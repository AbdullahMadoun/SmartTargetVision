from __future__ import annotations

from pathlib import Path

import cv2

from .engine import IdentityEngine
from .types import Enrollment, EnrollmentResult, ImageRunResult
from .visualize import draw_matches


class DroneIdentityPipeline:
    def __init__(self, config: dict, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)
        self._runtime_cfg = config.get("runtime", {})
        self._engine = IdentityEngine(config=config, root_dir=self._root_dir)
        self._threshold = self._engine.match_threshold

    def enroll(self, reference_paths: list[str], instruction: str | None = None) -> EnrollmentResult:
        return self._engine.create_target_profile(
            reference_paths=reference_paths,
            instruction=instruction,
        )

    @property
    def match_threshold(self) -> float:
        return self._threshold

    def reset_temporal_state(self) -> None:
        self._engine.reset_temporal_state()

    def run_on_bgr(self, detector_frame, enrollment: Enrollment, source_frame=None) -> ImageRunResult:
        source_frame = detector_frame if source_frame is None else source_frame
        analysis = self._engine.analyze_bgr(detector_frame, enrollment, source_frame=source_frame)
        annotated = draw_matches(detector_frame, analysis.matches, self._threshold)
        annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        return ImageRunResult(
            annotated_rgb=annotated_rgb,
            matches=analysis.matches,
            summary_text=analysis.summary_text,
        )

    def run_on_rgb(self, detector_frame_rgb, enrollment: Enrollment, source_frame_rgb=None) -> ImageRunResult:
        detector_frame_bgr = cv2.cvtColor(detector_frame_rgb, cv2.COLOR_RGB2BGR)
        source_frame_bgr = (
            detector_frame_bgr
            if source_frame_rgb is None
            else cv2.cvtColor(source_frame_rgb, cv2.COLOR_RGB2BGR)
        )
        return self.run_on_bgr(detector_frame_bgr, enrollment, source_frame=source_frame_bgr)

    def run_on_image(self, image_path: str, enrollment: Enrollment) -> ImageRunResult:
        source_frame = cv2.imread(str(image_path))
        if source_frame is None:
            raise FileNotFoundError(f"Could not read target image: {image_path}")
        detector_frame = _resize_for_detector(
            source_frame,
            int(self._runtime_cfg.get("probe_max_side", 768)),
        )
        return self.run_on_bgr(detector_frame, enrollment, source_frame=source_frame)


def _resize_for_detector(frame, max_side: int):
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return frame

    scale = max_side / float(longest)
    return cv2.resize(
        frame,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )
