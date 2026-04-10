"""
utils/display.py
Draws bounding boxes, labels, confidence scores, FPS, and the active
VLM vocabulary onto OpenCV frames.
"""

import time
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from detector.base import DetectionResult
from tracking import FollowState


# Colour palette: one colour per class name (deterministic via hash)
_PALETTE = [
    (86, 180, 233),   # sky blue
    (230, 159, 0),    # orange
    (0, 158, 115),    # teal
    (213, 94, 0),     # vermillion
    (204, 121, 167),  # pink
    (0, 114, 178),    # blue
    (240, 228, 66),   # yellow
]


def _color_for(label: str) -> tuple[int, int, int]:
    return _PALETTE[hash(label) % len(_PALETTE)]


@dataclass
class Renderer:
    """
    Stateful renderer — tracks FPS across frames and draws consistent overlays.
    """
    config: dict
    _timestamps: deque = field(default_factory=lambda: deque(maxlen=30))

    def draw(
        self,
        frame: np.ndarray,
        result: DetectionResult,
        active_classes: list[str],
        vlm_refresh_in: float,
        follow_state: FollowState | None = None,
    ) -> np.ndarray:
        """
        Annotate a frame in-place and return it.

        Args:
            frame:           BGR frame from camera.
            result:          Detection result for this frame.
            active_classes:  Classes currently loaded into YOLO-World.
            vlm_refresh_in:  Seconds until next VLM query (shown in HUD).

        Returns:
            Annotated BGR frame (same object, modified in-place).
        """
        self._timestamps.append(time.monotonic())

        cfg = self.config
        thickness = int(cfg.get("box_thickness", 2))
        font_scale = float(cfg.get("font_scale", 0.55))
        show_labels = cfg.get("show_labels", True)
        show_conf = cfg.get("show_confidence", True)
        show_fps = cfg.get("show_fps", True)

        # ── Bounding boxes ──────────────────────────────────────────── #
        for det in result.detections:
            x1, y1, x2, y2 = det.box
            color = _color_for(det.label)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

            if show_labels:
                text = f"{det.label} {det.confidence:.0%}" if show_conf else det.label
                (tw, th), baseline = cv2.getTextSize(
                    text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1
                )
                # Label background pill
                cv2.rectangle(
                    frame,
                    (x1, y1 - th - baseline - 4),
                    (x1 + tw + 6, y1),
                    color,
                    -1,
                )
                cv2.putText(
                    frame, text,
                    (x1 + 3, y1 - baseline - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                    (255, 255, 255), 1, cv2.LINE_AA,
                )

        if follow_state and follow_state.search_box and follow_state.search_mode == "roi":
            sx1, sy1, sx2, sy2 = follow_state.search_box
            search_color = (255, 210, 90)
            cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), search_color, 1)
            cv2.putText(
                frame,
                "ROI SEARCH",
                (sx1 + 4, max(14, sy1 + 14)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                search_color,
                1,
                cv2.LINE_AA,
            )

        if follow_state and follow_state.display_box:
            fx1, fy1, fx2, fy2 = follow_state.display_box
            follow_color = {
                "locked": (80, 220, 120),
                "acquiring": (70, 170, 255),
                "lost": (0, 180, 255),
            }.get(follow_state.status, (180, 180, 180))
            cv2.rectangle(frame, (fx1, fy1), (fx2, fy2), follow_color, thickness + 2)

            target = follow_state.target
            follow_text = f"{follow_state.status.upper()}"
            if target:
                follow_text += f" {target.label}"
                if target.track_id is not None:
                    follow_text += f" #{target.track_id}"

            (tw, th), baseline = cv2.getTextSize(
                follow_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale + 0.05, 1
            )
            pill_y1 = max(0, fy1 - th - baseline - 6)
            cv2.rectangle(
                frame,
                (fx1, pill_y1),
                (fx1 + tw + 8, max(0, fy1)),
                follow_color,
                -1,
            )
            cv2.putText(
                frame,
                follow_text,
                (fx1 + 4, max(th + 2, fy1 - baseline - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale + 0.05,
                (20, 20, 20),
                1,
                cv2.LINE_AA,
            )

        # ── HUD ─────────────────────────────────────────────────────── #
        if show_fps:
            fps = self._fps()
            cv2.putText(
                frame, f"FPS {fps:.1f}  |  inf {result.inference_ms:.0f}ms",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (200, 200, 200), 1, cv2.LINE_AA,
            )

        # VLM refresh countdown
        cv2.putText(
            frame,
            f"VLM refresh in {vlm_refresh_in:.0f}s  |  {len(active_classes)} classes",
            (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (160, 200, 160), 1, cv2.LINE_AA,
        )

        if follow_state:
            target = follow_state.target
            label = target.label if target else "-"
            track = (
                f"#{target.track_id}"
                if target and target.track_id is not None
                else "no-id"
            )
            cv2.putText(
                frame,
                (
                    f"Target {follow_state.status}  |  {label} {track}  |  "
                    f"hits {follow_state.hits}  |  missed {follow_state.missed_frames}"
                ),
                (10, 76),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (210, 210, 210),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                f"Search {follow_state.search_mode}  |  {follow_state.search_reason or '-'}",
                (10, 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (210, 210, 210),
                1,
                cv2.LINE_AA,
            )

        # Active classes strip at the bottom
        classes_str = ", ".join(active_classes[:12])
        if len(active_classes) > 12:
            classes_str += " …"
        h = frame.shape[0]
        cv2.rectangle(frame, (0, h - 30), (frame.shape[1], h), (30, 30, 30), -1)
        cv2.putText(
            frame, classes_str,
            (8, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (180, 220, 180), 1, cv2.LINE_AA,
        )

        return frame

    def _fps(self) -> float:
        if len(self._timestamps) < 2:
            return 0.0
        span = self._timestamps[-1] - self._timestamps[0]
        return (len(self._timestamps) - 1) / span if span > 0 else 0.0
