from __future__ import annotations

import cv2
import numpy as np

from .types import MatchResult


def draw_matches(frame: np.ndarray, matches: list[MatchResult], threshold: float) -> np.ndarray:
    canvas = frame.copy()
    if not matches:
        cv2.putText(
            canvas,
            "No face detected",
            (12, 56),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (80, 180, 255),
            2,
            cv2.LINE_AA,
        )

    for item in matches:
        x1, y1, x2, y2 = item.detection.box
        color = (0, 200, 0) if item.is_match else (0, 120, 255)
        status = "MATCH" if item.is_match else "NO MATCH"
        text = (
            f"{status} "
            f"cos {item.smoothed_similarity:.2f} "
            f"det {item.detection.confidence:.0%}"
        )
        if item.note and item.note not in {"Same face confirmed.", "Different face."}:
            text = f"{status} {item.note.lower()}"
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            canvas,
            text,
            (x1, max(18, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    cv2.putText(
        canvas,
        f"face match threshold {threshold:.2f}",
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (230, 230, 230),
        2,
        cv2.LINE_AA,
    )
    return canvas
