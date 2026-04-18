from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .flight_control import DroneStatus


StatusProvider = Callable[[str], DroneStatus]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ActiveRecording:
    recording_id: str
    drone_id: str
    started_at: str
    file_path: Path
    interval_s: float
    samples: list[dict[str, object]] = field(default_factory=list)
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    stopped_at: str | None = None


class FlightRecordingManager:
    def __init__(
        self,
        recordings_dir: Path,
        *,
        status_provider: StatusProvider,
    ) -> None:
        self._recordings_dir = recordings_dir
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        self._status_provider = status_provider
        self._active_by_id: dict[str, ActiveRecording] = {}
        self._active_by_drone: dict[str, str] = {}
        self._lock = threading.RLock()

    def start(self, *, drone_id: str, interval_s: float = 2.0) -> dict[str, object]:
        if interval_s <= 0:
            raise ValueError("interval_s must be greater than 0.")

        with self._lock:
            existing_id = self._active_by_drone.get(drone_id)
            if existing_id:
                existing = self._active_by_id[existing_id]
                return self._summary(existing, active=True)

            started_at = _utc_now()
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            recording_id = f"{stamp}-{drone_id}"
            file_path = self._recordings_dir / f"{recording_id}.json"
            session = ActiveRecording(
                recording_id=recording_id,
                drone_id=drone_id,
                started_at=started_at,
                file_path=file_path,
                interval_s=interval_s,
            )
            thread = threading.Thread(
                target=self._run_session,
                args=(session,),
                daemon=True,
                name=f"recording-{recording_id}",
            )
            session.thread = thread
            self._active_by_id[recording_id] = session
            self._active_by_drone[drone_id] = recording_id
            self._write_session_file(session)
            thread.start()
            return self._summary(session, active=True)

    def stop(
        self,
        *,
        recording_id: str = "",
        drone_id: str = "",
    ) -> dict[str, object]:
        with self._lock:
            session = self._resolve_active_session(recording_id=recording_id, drone_id=drone_id)
            if session is None:
                raise ValueError("No active recording matches the requested id or drone.")
            session.stop_event.set()
            thread = session.thread

        if thread is not None:
            thread.join(timeout=max(5.0, session.interval_s * 3.0))

        with self._lock:
            session.stopped_at = session.stopped_at or _utc_now()
            self._write_session_file(session)
            self._active_by_id.pop(session.recording_id, None)
            self._active_by_drone.pop(session.drone_id, None)
            return self._summary(session, active=False)

    def list_recordings(self) -> list[dict[str, object]]:
        recordings: list[dict[str, object]] = []
        for file_path in sorted(self._recordings_dir.glob("*.json"), reverse=True):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            summary = {
                "recording_id": payload.get("recording_id") or file_path.stem,
                "drone_id": payload.get("drone_id") or "drone-1",
                "started_at": payload.get("started_at"),
                "created_at": payload.get("started_at"),
                "stopped_at": payload.get("stopped_at"),
                "sample_count": len(payload.get("samples") or []),
                "file_path": str(file_path),
                "points": [
                    {
                        "lat": sample.get("latitude_deg"),
                        "lon": sample.get("longitude_deg"),
                        "alt": sample.get("relative_altitude_m"),
                        "battery": sample.get("battery_percent"),
                        "mode": sample.get("flight_mode"),
                    }
                    for sample in (payload.get("samples") or [])
                    if sample.get("latitude_deg") is not None and sample.get("longitude_deg") is not None
                ],
            }
            recordings.append(summary)
        return recordings

    def get_recording(self, recording_id: str) -> dict[str, object]:
        file_path = self._recordings_dir / f"{recording_id}.json"
        if not file_path.exists():
            raise ValueError(f"Recording not found: {recording_id}")
        return json.loads(file_path.read_text(encoding="utf-8"))

    def active_recordings(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                self._summary(session, active=True)
                for session in sorted(
                    self._active_by_id.values(),
                    key=lambda session: session.started_at,
                    reverse=True,
                )
            ]

    def _resolve_active_session(
        self,
        *,
        recording_id: str,
        drone_id: str,
    ) -> ActiveRecording | None:
        if recording_id:
            return self._active_by_id.get(recording_id)
        if drone_id:
            active_id = self._active_by_drone.get(drone_id)
            return self._active_by_id.get(active_id or "")
        if len(self._active_by_id) == 1:
            return next(iter(self._active_by_id.values()))
        return None

    def _run_session(self, session: ActiveRecording) -> None:
        while not session.stop_event.is_set():
            status = self._status_provider(session.drone_id)
            sample = {
                "captured_at": _utc_now(),
                **status.to_dict(),
            }
            with self._lock:
                session.samples.append(sample)
                self._write_session_file(session)
            session.stop_event.wait(session.interval_s)
        with self._lock:
            session.stopped_at = session.stopped_at or _utc_now()
            self._write_session_file(session)

    def _write_session_file(self, session: ActiveRecording) -> None:
        payload = {
            "recording_id": session.recording_id,
            "drone_id": session.drone_id,
            "started_at": session.started_at,
            "stopped_at": session.stopped_at,
            "interval_s": session.interval_s,
            "samples": session.samples,
        }
        session.file_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _summary(session: ActiveRecording, *, active: bool) -> dict[str, object]:
        return {
            "recording_id": session.recording_id,
            "drone_id": session.drone_id,
            "started_at": session.started_at,
            "stopped_at": session.stopped_at,
            "interval_s": session.interval_s,
            "sample_count": len(session.samples),
            "file_path": str(session.file_path),
            "active": active,
        }
