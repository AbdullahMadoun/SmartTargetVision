"""Flight control layer built on MAVSDK-Python."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Protocol

from .navigation import haversine_distance_m


logger = logging.getLogger(__name__)

DEFAULT_DRONE_ID = "drone-1"
DEFAULT_SYSTEM_ADDRESS = "udp://:14540"
CONNECT_TIMEOUT = 30
COMMAND_TIMEOUT = 30
POSITION_WAIT_TIMEOUT = 20
RECONNECT_DELAYS_S = (1.0, 2.0, 4.0)


@dataclass(frozen=True, slots=True)
class GeofenceSettings:
    max_altitude_m: float = 120.0
    max_distance_from_home_m: float = 500.0
    min_battery_percent_for_rtl: float = 20.0

    def to_dict(self) -> dict[str, float]:
        return {
            "max_altitude_m": self.max_altitude_m,
            "max_distance_from_home_m": self.max_distance_from_home_m,
            "min_battery_percent_for_rtl": self.min_battery_percent_for_rtl,
        }


@dataclass(frozen=True, slots=True)
class DroneStatus:
    connected: bool
    armed: bool
    in_air: bool
    latitude_deg: float
    longitude_deg: float
    absolute_altitude_m: float
    relative_altitude_m: float
    battery_percent: float
    flight_mode: str
    groundspeed_m_s: float = 0.0
    heading_deg: float = 0.0
    drone_id: str = DEFAULT_DRONE_ID
    home_latitude_deg: float | None = None
    home_longitude_deg: float | None = None
    home_absolute_altitude_m: float | None = None
    distance_from_home_m: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "connected": self.connected,
            "armed": self.armed,
            "in_air": self.in_air,
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "absolute_altitude_m": self.absolute_altitude_m,
            "relative_altitude_m": self.relative_altitude_m,
            "battery_percent": self.battery_percent,
            "flight_mode": self.flight_mode,
            "groundspeed_m_s": self.groundspeed_m_s,
            "heading_deg": self.heading_deg,
            "drone_id": self.drone_id,
            "home_latitude_deg": self.home_latitude_deg,
            "home_longitude_deg": self.home_longitude_deg,
            "home_absolute_altitude_m": self.home_absolute_altitude_m,
            "distance_from_home_m": self.distance_from_home_m,
        }

    def format(self) -> str:
        if not self.connected:
            return "Drone not connected."
        lines = [
            f"Drone ID: {self.drone_id}",
            f"Connected: yes",
            f"Armed: {'yes' if self.armed else 'no'}",
            f"In Air: {'yes' if self.in_air else 'no'}",
            f"Position: {self.latitude_deg:.6f}°N, {self.longitude_deg:.6f}°E",
            f"Absolute Altitude: {self.absolute_altitude_m:.1f} m",
            f"Relative Altitude: {self.relative_altitude_m:.1f} m",
            f"Ground Speed: {self.groundspeed_m_s:.1f} m/s",
            f"Heading: {self.heading_deg:.0f}°",
            f"Battery: {self.battery_percent:.0f}%",
            f"Flight Mode: {self.flight_mode}",
        ]
        if self.home_latitude_deg is not None and self.home_longitude_deg is not None:
            lines.append(f"Distance From Home: {self.distance_from_home_m:.1f} m")
        return "\n".join(lines)


@dataclass(slots=True)
class _DroneSession:
    drone_id: str
    address: str
    backend: "MavsdkBackend"
    connected: bool = False
    offboard_active: bool = False
    home_latitude_deg: float | None = None
    home_longitude_deg: float | None = None
    home_absolute_altitude_m: float | None = None


class MavsdkBackend(Protocol):
    async def connect(self, system_address: str) -> None: ...
    async def wait_for_connected(self, timeout: float) -> bool: ...
    async def wait_for_gps_ready(self, timeout: float) -> bool: ...
    async def arm(self) -> None: ...
    async def disarm(self) -> None: ...
    async def takeoff(self) -> None: ...
    async def land(self) -> None: ...
    async def set_takeoff_altitude(self, altitude_m: float) -> None: ...
    async def goto_location(
        self,
        latitude_deg: float,
        longitude_deg: float,
        absolute_altitude_m: float,
        yaw_deg: float,
    ) -> None: ...
    async def hold(self) -> None: ...
    async def return_to_launch(self) -> None: ...
    async def set_maximum_speed(self, speed_m_s: float) -> None: ...
    async def start_offboard(self) -> None: ...
    async def stop_offboard(self) -> None: ...
    async def set_velocity_body(
        self,
        forward_m_s: float,
        right_m_s: float,
        down_m_s: float,
        yaw_rate_deg_s: float,
    ) -> None: ...
    async def get_status(self) -> DroneStatus: ...


class RealMavsdkBackend:
    def __init__(self) -> None:
        self._system = None

    async def connect(self, system_address: str) -> None:
        from mavsdk import System

        self._system = System()
        await self._system.connect(system_address=system_address)

    async def wait_for_connected(self, timeout: float) -> bool:
        assert self._system is not None
        try:
            async for state in asyncio.wait_for(self._iter_connection(self._system), timeout=timeout):
                if state:
                    return True
        except asyncio.TimeoutError:
            pass
        return False

    @staticmethod
    async def _iter_connection(system) -> bool:
        async for state in system.core.connection_state():
            yield state.is_connected

    async def wait_for_gps_ready(self, timeout: float) -> bool:
        assert self._system is not None
        try:
            async for health in asyncio.wait_for(self._iter_health(self._system), timeout=timeout):
                if health:
                    return True
        except asyncio.TimeoutError:
            pass
        return False

    @staticmethod
    async def _iter_health(system) -> bool:
        async for health in system.telemetry.health():
            yield health.is_global_position_ok and health.is_home_position_ok

    async def arm(self) -> None:
        assert self._system is not None
        await self._system.action.arm()

    async def disarm(self) -> None:
        assert self._system is not None
        await self._system.action.disarm()

    async def takeoff(self) -> None:
        assert self._system is not None
        await self._system.action.takeoff()

    async def land(self) -> None:
        assert self._system is not None
        await self._system.action.land()

    async def set_takeoff_altitude(self, altitude_m: float) -> None:
        assert self._system is not None
        await self._system.action.set_takeoff_altitude(altitude_m)

    async def goto_location(
        self,
        latitude_deg: float,
        longitude_deg: float,
        absolute_altitude_m: float,
        yaw_deg: float,
    ) -> None:
        assert self._system is not None
        await self._system.action.goto_location(
            latitude_deg,
            longitude_deg,
            absolute_altitude_m,
            yaw_deg,
        )

    async def hold(self) -> None:
        assert self._system is not None
        await self._system.action.hold()

    async def return_to_launch(self) -> None:
        assert self._system is not None
        await self._system.action.return_to_launch()

    async def set_maximum_speed(self, speed_m_s: float) -> None:
        assert self._system is not None
        await self._system.action.set_maximum_speed(speed_m_s)

    async def start_offboard(self) -> None:
        assert self._system is not None
        from mavsdk.offboard import VelocityBodyYawspeed

        # PX4 requires a setpoint before offboard can be started.
        await self._system.offboard.set_velocity_body(
            VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
        )
        await self._system.offboard.start()

    async def stop_offboard(self) -> None:
        assert self._system is not None
        await self._system.offboard.stop()

    async def set_velocity_body(
        self,
        forward_m_s: float,
        right_m_s: float,
        down_m_s: float,
        yaw_rate_deg_s: float,
    ) -> None:
        assert self._system is not None
        from mavsdk.offboard import VelocityBodyYawspeed

        await self._system.offboard.set_velocity_body(
            VelocityBodyYawspeed(forward_m_s, right_m_s, down_m_s, yaw_rate_deg_s)
        )

    async def get_status(self) -> DroneStatus:
        assert self._system is not None
        position = await self._get_first(self._system.telemetry.position())
        battery = await self._get_first(self._system.telemetry.battery())
        flight_mode = await self._get_first(self._system.telemetry.flight_mode())
        armed = await self._get_first(self._system.telemetry.armed())
        in_air = await self._get_first(self._system.telemetry.in_air())

        groundspeed_m_s = 0.0
        heading_deg = 0.0
        try:
            velocity = await self._get_first(self._system.telemetry.velocity_ned())
            groundspeed_m_s = math.sqrt(
                float(getattr(velocity, "north_m_s", 0.0)) ** 2
                + float(getattr(velocity, "east_m_s", 0.0)) ** 2
                + float(getattr(velocity, "down_m_s", 0.0)) ** 2
            )
        except Exception:
            groundspeed_m_s = 0.0
        try:
            heading = await self._get_first(self._system.telemetry.heading())
            heading_deg = float(getattr(heading, "heading_deg", heading))
        except Exception:
            heading_deg = 0.0

        return DroneStatus(
            connected=True,
            armed=bool(armed),
            in_air=bool(in_air),
            latitude_deg=float(position.latitude_deg),
            longitude_deg=float(position.longitude_deg),
            absolute_altitude_m=float(position.absolute_altitude_m),
            relative_altitude_m=float(position.relative_altitude_m),
            battery_percent=float(battery.remaining_percent) * 100.0,
            flight_mode=str(flight_mode),
            groundspeed_m_s=groundspeed_m_s,
            heading_deg=heading_deg,
        )

    @staticmethod
    async def _get_first(async_gen):
        async for item in async_gen:
            return item


class DroneController:
    def __init__(
        self,
        address: str = DEFAULT_SYSTEM_ADDRESS,
        backend: MavsdkBackend | None = None,
        *,
        backend_factory: Callable[[], MavsdkBackend] | None = None,
        addresses: dict[str, str] | None = None,
    ) -> None:
        self._default_address = address
        self._configured_addresses = {
            key.strip(): value.strip()
            for key, value in (addresses or {}).items()
            if key.strip() and value.strip()
        }
        if DEFAULT_DRONE_ID not in self._configured_addresses:
            self._configured_addresses[DEFAULT_DRONE_ID] = address
        self._seed_backend = backend
        self._backend_factory = backend_factory or RealMavsdkBackend
        self._sessions: dict[str, _DroneSession] = {}
        self._geofence = GeofenceSettings()
        self._lock = threading.RLock()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="mavsdk-loop",
        )
        self._thread.start()

    def _run(self, coro, *, timeout: float = COMMAND_TIMEOUT):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def _normalize_drone_id(self, drone_id: str = "") -> str:
        normalized = drone_id.strip() or DEFAULT_DRONE_ID
        return normalized

    def _make_backend(self) -> MavsdkBackend:
        with self._lock:
            if self._seed_backend is not None:
                backend = self._seed_backend
                self._seed_backend = None
                return backend
        return self._backend_factory()

    def _session_for(self, drone_id: str = "") -> _DroneSession:
        normalized = self._normalize_drone_id(drone_id)
        with self._lock:
            session = self._sessions.get(normalized)
            if session is not None:
                return session
            session = _DroneSession(
                drone_id=normalized,
                address=self._configured_addresses.get(normalized, self._default_address),
                backend=self._make_backend(),
            )
            self._sessions[normalized] = session
            return session

    def _status_prefix(self, drone_id: str) -> str:
        return "" if drone_id == DEFAULT_DRONE_ID else f"[{drone_id}] "

    def _require_connected(self, drone_id: str = "") -> tuple[_DroneSession, str | None]:
        session = self._session_for(drone_id)
        if not session.connected:
            return session, f"❌ {self._status_prefix(session.drone_id)}Drone not connected. Call connect_drone first."
        return session, None

    def _call_backend(
        self,
        session: _DroneSession,
        operation: Callable[[MavsdkBackend], object],
        *,
        timeout: float = COMMAND_TIMEOUT,
        allow_reconnect: bool = True,
    ):
        try:
            return self._run(operation(session.backend), timeout=timeout)
        except Exception:
            logger.exception("backend call failed for %s", session.drone_id)
            if allow_reconnect and self._attempt_reconnect(session):
                return self._run(operation(session.backend), timeout=timeout)
            session.connected = False
            raise

    def _attempt_reconnect(self, session: _DroneSession) -> bool:
        target = session.address.strip()
        if not target:
            return False
        for delay_s in RECONNECT_DELAYS_S:
            time.sleep(delay_s)
            try:
                self._run(session.backend.connect(target), timeout=CONNECT_TIMEOUT)
                connected = self._run(
                    session.backend.wait_for_connected(CONNECT_TIMEOUT),
                    timeout=CONNECT_TIMEOUT + 5,
                )
                if connected:
                    session.connected = True
                    try:
                        self._capture_home(session)
                    except Exception:
                        logger.exception("home capture after reconnect failed for %s", session.drone_id)
                    return True
            except Exception:
                logger.exception("reconnect attempt failed for %s", session.drone_id)
        session.connected = False
        return False

    def _capture_home(self, session: _DroneSession) -> None:
        status = self._call_backend(
            session,
            lambda backend: backend.get_status(),
            timeout=COMMAND_TIMEOUT,
            allow_reconnect=False,
        )
        self._update_home(session, status)

    def _update_home(self, session: _DroneSession, status: DroneStatus) -> None:
        if session.home_latitude_deg is None:
            session.home_latitude_deg = status.latitude_deg
        if session.home_longitude_deg is None:
            session.home_longitude_deg = status.longitude_deg
        if session.home_absolute_altitude_m is None:
            session.home_absolute_altitude_m = (
                status.absolute_altitude_m - status.relative_altitude_m
            )

    def _enrich_status(self, session: _DroneSession, status: DroneStatus) -> DroneStatus:
        self._update_home(session, status)
        distance_from_home_m = 0.0
        if session.home_latitude_deg is not None and session.home_longitude_deg is not None:
            distance_from_home_m = haversine_distance_m(
                session.home_latitude_deg,
                session.home_longitude_deg,
                status.latitude_deg,
                status.longitude_deg,
            )
        return replace(
            status,
            drone_id=session.drone_id,
            home_latitude_deg=session.home_latitude_deg,
            home_longitude_deg=session.home_longitude_deg,
            home_absolute_altitude_m=session.home_absolute_altitude_m,
            distance_from_home_m=distance_from_home_m,
        )

    def _disconnected_status(self, session: _DroneSession) -> DroneStatus:
        session.offboard_active = False
        return DroneStatus(
            connected=False,
            armed=False,
            in_air=False,
            latitude_deg=0.0,
            longitude_deg=0.0,
            absolute_altitude_m=0.0,
            relative_altitude_m=0.0,
            battery_percent=0.0,
            flight_mode="UNKNOWN",
            drone_id=session.drone_id,
            home_latitude_deg=session.home_latitude_deg,
            home_longitude_deg=session.home_longitude_deg,
            home_absolute_altitude_m=session.home_absolute_altitude_m,
            distance_from_home_m=0.0,
        )

    def _absolute_altitude_for(self, session: _DroneSession, status: DroneStatus, relative_altitude_m: float) -> float:
        if session.home_absolute_altitude_m is not None:
            return session.home_absolute_altitude_m + relative_altitude_m
        return status.absolute_altitude_m - status.relative_altitude_m + relative_altitude_m

    def _ensure_offboard_stopped(self, session: _DroneSession) -> None:
        if not session.offboard_active:
            return
        try:
            self._call_backend(session, lambda backend: backend.stop_offboard())
        finally:
            session.offboard_active = False

    def list_drones(self) -> list[str]:
        known = set(self._configured_addresses)
        known.update(self._sessions)
        return sorted(known)

    def get_geofence(self) -> GeofenceSettings:
        return self._geofence

    def set_geofence(
        self,
        *,
        max_altitude_m: float | None = None,
        max_distance_from_home_m: float | None = None,
        min_battery_percent_for_rtl: float | None = None,
    ) -> GeofenceSettings:
        current = self._geofence
        updated = GeofenceSettings(
            max_altitude_m=max_altitude_m if max_altitude_m is not None else current.max_altitude_m,
            max_distance_from_home_m=(
                max_distance_from_home_m
                if max_distance_from_home_m is not None
                else current.max_distance_from_home_m
            ),
            min_battery_percent_for_rtl=(
                min_battery_percent_for_rtl
                if min_battery_percent_for_rtl is not None
                else current.min_battery_percent_for_rtl
            ),
        )
        if updated.max_altitude_m <= 0:
            raise ValueError("max_altitude_m must be greater than 0.")
        if updated.max_distance_from_home_m <= 0:
            raise ValueError("max_distance_from_home_m must be greater than 0.")
        if updated.min_battery_percent_for_rtl < 0 or updated.min_battery_percent_for_rtl > 100:
            raise ValueError("min_battery_percent_for_rtl must be between 0 and 100.")
        self._geofence = updated
        return updated

    def connect(self, address: str = "", drone_id: str = "") -> str:
        session = self._session_for(drone_id)
        target = address.strip() or session.address or self._default_address
        session.address = target
        try:
            self._run(session.backend.connect(target), timeout=CONNECT_TIMEOUT)
            connected = self._run(
                session.backend.wait_for_connected(CONNECT_TIMEOUT),
                timeout=CONNECT_TIMEOUT + 5,
            )
            if not connected:
                return f"❌ {self._status_prefix(session.drone_id)}Timed out waiting for PX4 connection."
            session.connected = True
            gps_ok = self._run(
                session.backend.wait_for_gps_ready(POSITION_WAIT_TIMEOUT),
                timeout=POSITION_WAIT_TIMEOUT + 5,
            )
            try:
                self._capture_home(session)
            except Exception:
                logger.exception("initial home capture failed for %s", session.drone_id)
            gps_text = "GPS: ready" if gps_ok else "GPS: waiting (may need more time)"
            return (
                f"✅ {self._status_prefix(session.drone_id)}Connected to PX4 at {target}. "
                f"{gps_text}."
            )
        except Exception as exc:
            session.connected = False
            logger.exception("connect failed for %s", session.drone_id)
            return f"❌ {self._status_prefix(session.drone_id)}Connection error: {exc}"

    def arm(self, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        try:
            self._call_backend(session, lambda backend: backend.arm())
            return f"✅ {self._status_prefix(session.drone_id)}Drone armed."
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}Arm failed: {exc}"

    def disarm(self, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        try:
            self._call_backend(session, lambda backend: backend.disarm())
            return f"✅ {self._status_prefix(session.drone_id)}Drone disarmed."
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}Disarm failed: {exc}"

    def takeoff(self, altitude_m: float = 5.0, *, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        self._ensure_offboard_stopped(session)
        if altitude_m > self._geofence.max_altitude_m:
            return (
                f"❌ {self._status_prefix(session.drone_id)}Takeoff blocked by geofence: "
                f"max altitude is {self._geofence.max_altitude_m:.1f} m."
            )
        status = self.get_status_snapshot(drone_id=session.drone_id)
        if not status.connected:
            return f"❌ {self._status_prefix(session.drone_id)}Status read failed before takeoff."
        if status.battery_percent < self._geofence.min_battery_percent_for_rtl:
            return (
                f"❌ {self._status_prefix(session.drone_id)}Takeoff blocked: battery {status.battery_percent:.0f}% "
                f"is below the RTL reserve of {self._geofence.min_battery_percent_for_rtl:.0f}%."
            )
        try:
            self._call_backend(session, lambda backend: backend.set_takeoff_altitude(altitude_m))
            self._call_backend(session, lambda backend: backend.arm())
            self._call_backend(session, lambda backend: backend.takeoff())
            return (
                f"✅ {self._status_prefix(session.drone_id)}Takeoff initiated to {altitude_m:.1f} m."
            )
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}Takeoff failed: {exc}"

    def land(self, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        self._ensure_offboard_stopped(session)
        try:
            self._call_backend(session, lambda backend: backend.land())
            return f"✅ {self._status_prefix(session.drone_id)}Landing initiated."
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}Land failed: {exc}"

    def go_to_location(
        self,
        latitude_deg: float,
        longitude_deg: float,
        altitude_m: float = 10.0,
        yaw_deg: float = 0.0,
        *,
        drone_id: str = "",
    ) -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        self._ensure_offboard_stopped(session)

        status = self.get_status_snapshot(drone_id=session.drone_id)
        if not status.connected:
            return f"❌ {self._status_prefix(session.drone_id)}Status read failed before go-to."
        if altitude_m > self._geofence.max_altitude_m:
            return (
                f"❌ {self._status_prefix(session.drone_id)}Go-to blocked by geofence: "
                f"max altitude is {self._geofence.max_altitude_m:.1f} m."
            )
        if status.battery_percent < self._geofence.min_battery_percent_for_rtl:
            return (
                f"❌ {self._status_prefix(session.drone_id)}Go-to blocked: battery {status.battery_percent:.0f}% "
                f"is below the RTL reserve of {self._geofence.min_battery_percent_for_rtl:.0f}%."
            )

        home_latitude_deg = session.home_latitude_deg or status.latitude_deg
        home_longitude_deg = session.home_longitude_deg or status.longitude_deg
        target_distance_m = haversine_distance_m(
            home_latitude_deg,
            home_longitude_deg,
            latitude_deg,
            longitude_deg,
        )
        if target_distance_m > self._geofence.max_distance_from_home_m:
            return (
                f"❌ {self._status_prefix(session.drone_id)}Go-to blocked by geofence: "
                f"target is {target_distance_m:.1f} m from home, limit is "
                f"{self._geofence.max_distance_from_home_m:.1f} m."
            )

        absolute_altitude_m = self._absolute_altitude_for(session, status, altitude_m)
        try:
            self._call_backend(
                session,
                lambda backend: backend.goto_location(
                    latitude_deg,
                    longitude_deg,
                    absolute_altitude_m,
                    yaw_deg,
                ),
            )
            return (
                f"✅ {self._status_prefix(session.drone_id)}Flying to "
                f"({latitude_deg:.6f}, {longitude_deg:.6f}) at {altitude_m:.1f} m altitude."
            )
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}Go-to failed: {exc}"

    def hold_position(self, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        self._ensure_offboard_stopped(session)
        try:
            self._call_backend(session, lambda backend: backend.hold())
            return f"✅ {self._status_prefix(session.drone_id)}Holding position."
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}Hold failed: {exc}"

    def return_to_launch(self, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        self._ensure_offboard_stopped(session)
        try:
            self._call_backend(session, lambda backend: backend.return_to_launch())
            return f"✅ {self._status_prefix(session.drone_id)}Returning to launch point."
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}RTL failed: {exc}"

    def get_status_snapshot(self, drone_id: str = "") -> DroneStatus:
        session = self._session_for(drone_id)
        if not session.connected:
            return self._disconnected_status(session)
        try:
            status = self._call_backend(session, lambda backend: backend.get_status())
            return self._enrich_status(session, status)
        except Exception:
            return self._disconnected_status(session)

    def get_status(self, drone_id: str = "") -> str:
        status = self.get_status_snapshot(drone_id)
        if not status.connected:
            return f"❌ {self._status_prefix(status.drone_id)}Drone not connected. Call connect_drone first."
        return f"📡 Drone Status:\n{status.format()}"

    def set_maximum_speed(self, speed_m_s: float = 5.0, *, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        try:
            self._call_backend(session, lambda backend: backend.set_maximum_speed(speed_m_s))
            return (
                f"✅ {self._status_prefix(session.drone_id)}Maximum speed set to {speed_m_s:.1f} m/s."
            )
        except Exception as exc:
            return f"❌ {self._status_prefix(session.drone_id)}Set speed failed: {exc}"

    def send_body_velocity(
        self,
        *,
        forward_m_s: float,
        right_m_s: float,
        down_m_s: float,
        yaw_rate_deg_s: float,
        drone_id: str = "",
    ) -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        try:
            if not session.offboard_active:
                self._call_backend(session, lambda backend: backend.start_offboard())
                session.offboard_active = True
            self._call_backend(
                session,
                lambda backend: backend.set_velocity_body(
                    forward_m_s,
                    right_m_s,
                    down_m_s,
                    yaw_rate_deg_s,
                ),
            )
            return (
                f"✅ {self._status_prefix(session.drone_id)}Body velocity command applied: "
                f"forward={forward_m_s:.2f} m/s, right={right_m_s:.2f} m/s, "
                f"down={down_m_s:.2f} m/s, yaw_rate={yaw_rate_deg_s:.1f} deg/s."
            )
        except Exception as exc:
            session.offboard_active = False
            return f"❌ {self._status_prefix(session.drone_id)}Body velocity failed: {exc}"

    def stop_body_velocity_control(self, drone_id: str = "") -> str:
        session, err = self._require_connected(drone_id)
        if err:
            return err
        if not session.offboard_active:
            return f"✅ {self._status_prefix(session.drone_id)}Offboard body control already stopped."
        try:
            self._call_backend(session, lambda backend: backend.stop_offboard())
            session.offboard_active = False
            return f"✅ {self._status_prefix(session.drone_id)}Offboard body control stopped."
        except Exception as exc:
            session.offboard_active = False
            return f"❌ {self._status_prefix(session.drone_id)}Stop offboard failed: {exc}"

    def wait_until_arrival(
        self,
        *,
        drone_id: str = "",
        latitude_deg: float,
        longitude_deg: float,
        altitude_m: float,
        horizontal_tolerance_m: float = 4.0,
        vertical_tolerance_m: float = 3.0,
        timeout_s: float = 180.0,
        poll_interval_s: float = 2.0,
    ) -> DroneStatus:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = self.get_status_snapshot(drone_id)
            if status.connected:
                horizontal_error_m = haversine_distance_m(
                    status.latitude_deg,
                    status.longitude_deg,
                    latitude_deg,
                    longitude_deg,
                )
                vertical_error_m = abs(status.relative_altitude_m - altitude_m)
                if horizontal_error_m <= horizontal_tolerance_m and vertical_error_m <= vertical_tolerance_m:
                    return status
            time.sleep(poll_interval_s)
        raise TimeoutError("Timed out waiting for the drone to reach the requested waypoint.")

    def shutdown(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
