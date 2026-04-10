from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .detector import PromptableDetector
from .embedder import ImageEmbedder
from .matcher import TemporalMatcher
from .planner import DetectorPromptPlanner
from .types import Detection, Enrollment, EnrollmentResult, FrameAnalysis, MatchResult, PromptPlan


class IdentityEngine:
    """
    Face-first identity engine:
    YOLO detects faces on a reduced-resolution frame, then each detected box is
    mapped back onto the original source frame so FaceNet receives a higher-
    resolution face crop for embedding and cosine similarity matching.
    """

    def __init__(self, config: dict, root_dir: str | Path) -> None:
        self._cfg = config
        self._root_dir = Path(root_dir)
        detector_cfg = config["detector"]
        self._fallback_classes = list(detector_cfg.get("fallback_classes", ["face"]))
        vlm_cfg = config.get("vlm", {"enabled": False})
        self._planner = (
            DetectorPromptPlanner(vlm_cfg, self._fallback_classes)
            if bool(vlm_cfg.get("enabled", False))
            else None
        )
        self._detector = PromptableDetector(detector_cfg, self._root_dir)
        self._embedder = ImageEmbedder(config["embedder"])
        self._matcher = TemporalMatcher(
            threshold=config["matching"]["threshold"],
            window=config["matching"]["smoothing_window"],
        )
        self._threshold = float(config["matching"]["threshold"])
        self._max_candidates = int(config["matching"].get("max_candidates_per_frame", 4))
        runtime_cfg = config.get("runtime", {})
        self._reference_detect_max_side = int(
            runtime_cfg.get(
                "reference_detect_max_side",
                runtime_cfg.get("probe_max_side", 768),
            )
        )
        self._reference_fallback = bool(
            config["embedder"].get("allow_full_frame_reference_fallback", False)
        )

    @property
    def match_threshold(self) -> float:
        return self._threshold

    def reset_temporal_state(self) -> None:
        self._matcher = TemporalMatcher(
            threshold=self._threshold,
            window=self._cfg["matching"]["smoothing_window"],
        )

    def plan_detector_prompts(
        self,
        reference_path: str,
        instruction: str | None = None,
        main_label: str = "",
        support_labels: str | list[str] | None = None,
    ) -> PromptPlan:
        if self._planner is None:
            return PromptPlan(
                classes=list(self._fallback_classes),
                raw_vlm="",
                main_class=self._fallback_classes[0] if self._fallback_classes else "",
                support_classes=list(self._fallback_classes[1:]),
                instruction=instruction or "",
                source="face_defaults",
            )

        if main_label or support_labels:
            return self._planner.plan_from_manual_labels(
                main_label=main_label,
                support_labels=support_labels,
                instruction=instruction or "",
            )

        return self._planner.plan_from_reference(
            reference_path=reference_path,
            instruction=instruction,
        )

    def create_target_profile(
        self,
        reference_paths: list[str],
        instruction: str | None = None,
        main_label: str = "",
        support_labels: str | list[str] | None = None,
    ) -> EnrollmentResult:
        if not reference_paths:
            raise ValueError("At least one reference image is required.")

        prompt_plan = self.plan_detector_prompts(
            reference_path=reference_paths[0],
            instruction=instruction,
            main_label=main_label,
            support_labels=support_labels,
        )

        active_classes = self._detector.set_classes(prompt_plan.classes or self._fallback_classes)
        vectors: list[np.ndarray] = []
        accepted_paths: list[str] = []
        rejected_paths: list[str] = []
        for path in reference_paths:
            try:
                vectors.append(self._embed_reference(path))
                accepted_paths.append(path)
            except ValueError:
                rejected_paths.append(path)

        if not vectors:
            raise ValueError(
                "No usable face was found in the reference images. Use a clear face photo."
            )

        enrollment_embedding = _normalize(np.mean(np.stack(vectors, axis=0), axis=0))
        enrollment = Enrollment(
            embedding=enrollment_embedding,
            reference_paths=list(accepted_paths),
            classes=list(active_classes),
            raw_vlm=prompt_plan.raw_vlm if self._planner is not None else "",
            prompt_plan=prompt_plan,
        )
        rejected_line = (
            f"\nSkipped {len(rejected_paths)} reference image(s) with no detected face."
            if rejected_paths
            else ""
        )
        summary = (
            f"Face profile built from {len(accepted_paths)} reference image(s).\n"
            f"Detector class: {', '.join(active_classes)}\n"
            f"Verifier: FaceNet cosine similarity\n"
            f"Match threshold: {self._threshold:.2f}"
            f"{rejected_line}"
        )
        return EnrollmentResult(
            enrollment=enrollment,
            classes=list(active_classes),
            raw_vlm=prompt_plan.raw_vlm if self._planner is not None else "",
            summary_text=summary,
        )

    def override_profile_labels(
        self,
        enrollment: Enrollment,
        main_label: str = "",
        support_labels: str | list[str] | None = None,
    ) -> Enrollment:
        if self._planner is None:
            return enrollment

        prompt_plan = self._planner.apply_overrides(
            enrollment.prompt_plan or self._planner.plan_from_manual_labels(
                main_label=enrollment.main_class,
                support_labels=enrollment.support_classes,
                raw_vlm=enrollment.raw_vlm,
            ),
            main_label=main_label,
            support_labels=support_labels,
        )
        return Enrollment(
            embedding=enrollment.embedding,
            reference_paths=list(enrollment.reference_paths),
            classes=list(prompt_plan.classes),
            raw_vlm=prompt_plan.raw_vlm,
            prompt_plan=prompt_plan,
        )

    def analyze_bgr(
        self,
        detector_frame: np.ndarray,
        enrollment: Enrollment,
        source_frame: np.ndarray | None = None,
    ) -> FrameAnalysis:
        source_frame = detector_frame if source_frame is None else source_frame
        active_classes = self._detector.set_classes(enrollment.classes or self._fallback_classes)
        detections = self._detector.detect(detector_frame)
        matches = self._match_detections(
            detector_frame=detector_frame,
            source_frame=source_frame,
            detections=detections,
            enrollment=enrollment,
        )
        return FrameAnalysis(
            detections=detections,
            matches=matches,
            classes_used=list(active_classes),
            summary_text=_summarize(matches),
            best_match=matches[0] if matches else None,
        )

    def analyze_image(self, image_path: str, enrollment: Enrollment) -> FrameAnalysis:
        source_frame = cv2.imread(str(image_path))
        if source_frame is None:
            raise FileNotFoundError(f"Could not read target image: {image_path}")
        detector_frame = _resize_for_detector(source_frame, self._reference_detect_max_side)
        return self.analyze_bgr(detector_frame, enrollment, source_frame=source_frame)

    def _match_detections(
        self,
        detector_frame: np.ndarray,
        source_frame: np.ndarray,
        detections: list[Detection],
        enrollment: Enrollment,
    ) -> list[MatchResult]:
        matches: list[MatchResult] = []
        ranked = sorted(detections, key=lambda item: item.confidence, reverse=True)
        detector_shape = detector_frame.shape[:2]
        source_shape = source_frame.shape[:2]

        for det in ranked[: self._max_candidates]:
            key = _face_key(det.box)
            source_box = _map_box_between_frames(det.box, detector_shape, source_shape)
            source_box = _expand_box(source_box, source_shape)
            crop = _crop(source_frame, source_box)
            if crop.size == 0:
                self._matcher.clear(key)
                continue

            query = self._embedder.embed_detected_face_bgr(crop)
            if query is None:
                self._matcher.clear(key)
                matches.append(
                    MatchResult(
                        detection=det,
                        similarity=0.0,
                        smoothed_similarity=0.0,
                        is_match=False,
                        face_box=det.box,
                        face_confidence=det.confidence,
                        note="Detected face crop could not be embedded.",
                    )
                )
                continue

            similarity, smoothed, is_match = self._matcher.compare(
                query,
                enrollment.embedding,
                key,
            )
            matches.append(
                MatchResult(
                    detection=det,
                    similarity=similarity,
                    smoothed_similarity=smoothed,
                    is_match=is_match,
                    face_box=det.box,
                    face_confidence=det.confidence,
                    note="Same face confirmed." if is_match else "Different face.",
                )
            )

        matches.sort(
            key=lambda item: (item.smoothed_similarity, item.detection.confidence),
            reverse=True,
        )
        return matches

    def _embed_reference(self, image_path: str) -> np.ndarray:
        source_frame = cv2.imread(str(image_path))
        if source_frame is None:
            raise FileNotFoundError(f"Could not read reference image: {image_path}")

        detector_frame = _resize_for_detector(source_frame, self._reference_detect_max_side)
        self._detector.set_classes(self._fallback_classes)
        detections = self._detector.detect(detector_frame)
        ranked = sorted(detections, key=lambda item: item.confidence, reverse=True)

        detector_shape = detector_frame.shape[:2]
        source_shape = source_frame.shape[:2]
        for det in ranked:
            source_box = _map_box_between_frames(det.box, detector_shape, source_shape)
            source_box = _expand_box(source_box, source_shape)
            crop = _crop(source_frame, source_box)
            if crop.size == 0:
                continue
            query = self._embedder.embed_detected_face_bgr(crop)
            if query is not None:
                return query

        if self._reference_fallback:
            query = self._embedder.embed_face_bgr(source_frame)
            if query is not None:
                return query

        raise ValueError(f"No usable face found in reference image: {image_path}")


def _crop(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = box
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    return frame[y1:y2, x1:x2]


def _normalize(vector: np.ndarray) -> np.ndarray:
    vector = vector.astype(np.float32)
    return vector / (np.linalg.norm(vector) + 1e-12)


def _summarize(matches: list[MatchResult]) -> str:
    if not matches:
        return "No face detected."

    lines: list[str] = []
    for item in matches:
        status = "MATCH" if item.is_match else "NO MATCH"
        line = (
            f"{status} | {item.detection.label} | "
            f"det={item.detection.confidence:.0%} | "
            f"cos={item.similarity:.2f} | smooth={item.smoothed_similarity:.2f} | "
            f"face={item.detection.box}"
        )
        if item.note and item.note not in {"Same face confirmed.", "Different face."}:
            line = f"{line} | {item.note}"
        lines.append(line)
    return "\n".join(lines)


def _resize_for_detector(frame: np.ndarray, max_side: int) -> np.ndarray:
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


def _map_box_between_frames(
    box: tuple[int, int, int, int],
    from_shape: tuple[int, int],
    to_shape: tuple[int, int],
) -> tuple[int, int, int, int]:
    from_height, from_width = from_shape
    to_height, to_width = to_shape
    scale_x = to_width / float(from_width)
    scale_y = to_height / float(from_height)
    x1, y1, x2, y2 = box
    mapped = (
        int(np.floor(x1 * scale_x)),
        int(np.floor(y1 * scale_y)),
        int(np.ceil(x2 * scale_x)),
        int(np.ceil(y2 * scale_y)),
    )
    return _clip_box(mapped, to_shape)


def _expand_box(
    box: tuple[int, int, int, int],
    frame_shape: tuple[int, int],
    scale: float = 0.18,
) -> tuple[int, int, int, int]:
    frame_height, frame_width = frame_shape
    x1, y1, x2, y2 = box
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    pad_x = int(round(width * scale))
    pad_y = int(round(height * scale))
    return _clip_box(
        (
            x1 - pad_x,
            y1 - pad_y,
            x2 + pad_x,
            y2 + pad_y,
        ),
        (frame_height, frame_width),
    )


def _clip_box(
    box: tuple[int, int, int, int],
    frame_shape: tuple[int, int],
) -> tuple[int, int, int, int]:
    frame_height, frame_width = frame_shape
    x1, y1, x2, y2 = box
    x1 = max(0, min(frame_width, x1))
    x2 = max(0, min(frame_width, x2))
    y1 = max(0, min(frame_height, y1))
    y2 = max(0, min(frame_height, y2))
    return x1, y1, x2, y2


def _face_key(box: tuple[int, int, int, int], cell_size: int = 64) -> str:
    x1, y1, x2, y2 = box
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    return (
        f"face:{center_x // cell_size}:{center_y // cell_size}:"
        f"{width // cell_size}:{height // cell_size}"
    )
