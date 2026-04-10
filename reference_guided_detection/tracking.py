"""
Single-target follow state for live open-vocabulary detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from detector.base import Detection


@dataclass
class SearchPlan:
    """Pre-detection search strategy for the next live frame."""

    mode: str = "global"
    roi_box: tuple[int, int, int, int] | None = None
    reason: str = ""


@dataclass
class FollowState:
    """Follower output for rendering and UI summaries."""

    status: str = "idle"
    target: Detection | None = None
    display_box: tuple[int, int, int, int] | None = None
    predicted_box: tuple[int, int, int, int] | None = None
    hits: int = 0
    missed_frames: int = 0
    score: float = 0.0
    message: str = ""
    search_mode: str = "global"
    search_box: tuple[int, int, int, int] | None = None
    search_reason: str = ""


class TargetFollower:
    """
    Maintains a soft lock on a single target across live detections.

    The detector stays responsible for candidate generation. This layer adds
    temporal state, duplicate merging for open-vocabulary prompts, brief miss
    tolerance, and target selection using confidence, label preference, motion
    continuity, box shape, IoU, and tracker IDs when they are available.
    """

    def __init__(self, config: dict | None = None) -> None:
        cfg = dict(config or {})
        self._enabled = bool(cfg.get("enabled", True))
        self._use_roi_search = bool(cfg.get("use_roi_search", False))
        self._acquire_hits = max(1, int(cfg.get("acquire_hits", 3)))
        self._max_missed = max(1, int(cfg.get("max_missed_frames", 8)))
        self._alpha = float(cfg.get("smoothing_alpha", 0.35))
        self._max_center_distance_ratio = float(cfg.get("max_center_distance_ratio", 0.25))
        self._min_detection_conf = float(cfg.get("min_detection_confidence", 0.05))
        self._primary_label_bonus = float(cfg.get("primary_label_bonus", 0.35))
        self._support_label_bonus = float(cfg.get("support_label_bonus", 0.16))
        self._label_stability_bonus = float(cfg.get("label_stability_bonus", 0.18))
        self._track_id_bonus = float(cfg.get("track_id_bonus", 0.8))
        self._iou_bonus = float(cfg.get("iou_bonus", 0.25))
        self._area_consistency_bonus = float(cfg.get("area_consistency_bonus", 0.18))
        self._aspect_consistency_bonus = float(cfg.get("aspect_consistency_bonus", 0.12))
        self._max_area_ratio = max(1.1, float(cfg.get("max_area_ratio", 2.4)))
        self._max_aspect_ratio = max(1.05, float(cfg.get("max_aspect_ratio", 1.8)))
        self._switch_margin = float(cfg.get("switch_margin", 0.22))
        self._strong_detection_confidence = float(cfg.get("strong_detection_confidence", 0.35))
        self._merge_duplicates = bool(cfg.get("merge_duplicate_detections", True))
        self._merge_iou_threshold = float(cfg.get("merge_iou_threshold", 0.72))
        self._merge_center_distance_ratio = float(
            cfg.get("merge_center_distance_ratio", 0.18)
        )
        self._consensus_confidence_bonus = float(cfg.get("consensus_confidence_bonus", 0.08))
        self._roi_padding_ratio = float(cfg.get("roi_padding_ratio", 0.35))
        self._lost_roi_padding_ratio = float(cfg.get("lost_roi_padding_ratio", 0.85))
        self._roi_min_size = max(32, int(cfg.get("roi_min_size", 160)))
        self._roi_max_size_ratio = float(cfg.get("roi_max_size_ratio", 0.75))
        self._global_refresh_interval = max(1, int(cfg.get("global_refresh_interval", 12)))
        self._max_roi_missed_before_global = max(
            1,
            int(cfg.get("max_roi_missed_before_global", 2)),
        )
        self._roi_min_hits = max(
            self._acquire_hits,
            int(cfg.get("roi_min_hits", self._acquire_hits + 1)),
        )
        self.reset()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        self._status = "idle"
        self._target: Detection | None = None
        self._preferred_label = ""
        self._smoothed_box: tuple[int, int, int, int] | None = None
        self._predicted_box: tuple[int, int, int, int] | None = None
        self._velocity = (0.0, 0.0, 0.0, 0.0)
        self._hits = 0
        self._missed = 0
        self._score = 0.0
        self._last_search_plan = SearchPlan(mode="global", reason="idle")

    def plan_search(self, frame_shape: tuple[int, ...], frame_index: int) -> SearchPlan:
        """
        Decide whether the next webcam frame should use global detection or a
        tighter ROI around the predicted target location.
        """
        if not self._enabled:
            self._last_search_plan = SearchPlan(mode="global", reason="disabled")
            return self._last_search_plan

        if not self._use_roi_search:
            reason = "full-frame"
            if self._status == "idle" or self._target is None:
                reason = "acquire"
            elif self._status == "acquiring":
                reason = "confirm-lock"
            elif self._status == "lost":
                reason = "reacquire-global"
            self._last_search_plan = SearchPlan(mode="global", reason=reason)
            return self._last_search_plan

        if self._target is None or self._status == "idle":
            self._last_search_plan = SearchPlan(mode="global", reason="acquire")
            return self._last_search_plan

        if self._status == "acquiring":
            self._last_search_plan = SearchPlan(mode="global", reason="confirm-lock")
            return self._last_search_plan

        periodic_global = (frame_index % self._global_refresh_interval) == 0
        if (
            self._status == "locked"
            and self._missed == 0
            and self._hits >= self._roi_min_hits
            and not periodic_global
        ):
            roi_box = self._build_search_box(frame_shape, lost=False)
            if roi_box is not None:
                self._last_search_plan = SearchPlan(
                    mode="roi",
                    roi_box=roi_box,
                    reason="locked-local",
                )
                return self._last_search_plan

        if self._status == "lost" and self._missed < self._max_roi_missed_before_global:
            roi_box = self._build_search_box(frame_shape, lost=True)
            if roi_box is not None:
                self._last_search_plan = SearchPlan(
                    mode="roi",
                    roi_box=roi_box,
                    reason="reacquire-local",
                )
                return self._last_search_plan

        reason = "refresh-global" if periodic_global else "reacquire-global"
        self._last_search_plan = SearchPlan(mode="global", reason=reason)
        return self._last_search_plan

    def update(
        self,
        detections: list[Detection],
        frame_shape: tuple[int, ...],
        active_classes: list[str] | None = None,
        prepared: bool = False,
    ) -> FollowState:
        if not self._enabled:
            return FollowState(status="disabled", message="Target follower disabled.")

        active = list(active_classes or [])
        candidates = (
            list(detections)
            if prepared
            else self._prepare_candidates(detections, frame_shape, active)
        )
        if not candidates:
            return self._on_miss(frame_shape)

        candidate, score = self._pick_candidate(candidates, frame_shape, active)
        if candidate is None:
            return self._on_miss(frame_shape)
        return self._on_hit(candidate, frame_shape, score)

    def refine_detections(
        self,
        detections: list[Detection],
        frame_shape: tuple[int, ...],
        active_classes: list[str] | None = None,
    ) -> list[Detection]:
        """Merge duplicate open-vocabulary boxes before rendering or tracking."""
        return self._prepare_candidates(detections, frame_shape, list(active_classes or []))

    def _prepare_candidates(
        self,
        detections: list[Detection],
        frame_shape: tuple[int, ...],
        active_classes: list[str],
    ) -> list[Detection]:
        filtered = [
            det
            for det in detections
            if det.confidence >= self._min_detection_conf and _area(det.box) > 0.0
        ]
        if len(filtered) < 2 or not self._merge_duplicates:
            return filtered
        return self._merge_overlapping_detections(filtered, frame_shape, active_classes)

    def _merge_overlapping_detections(
        self,
        detections: list[Detection],
        frame_shape: tuple[int, ...],
        active_classes: list[str],
    ) -> list[Detection]:
        pending = sorted(detections, key=lambda det: det.confidence, reverse=True)
        merged: list[Detection] = []

        while pending:
            cluster = [pending.pop(0)]
            expanded = True
            while expanded:
                expanded = False
                keep: list[Detection] = []
                for det in pending:
                    if any(self._should_merge_detections(existing, det) for existing in cluster):
                        cluster.append(det)
                        expanded = True
                    else:
                        keep.append(det)
                pending = keep
            merged.append(self._merge_cluster(cluster, frame_shape, active_classes))

        return sorted(merged, key=lambda det: det.confidence, reverse=True)

    def _should_merge_detections(self, det_a: Detection, det_b: Detection) -> bool:
        iou = _iou(det_a.box, det_b.box)
        if iou >= self._merge_iou_threshold:
            return True

        overlap_small = _overlap_on_smaller(det_a.box, det_b.box)
        if overlap_small <= 0.0:
            return False

        dist = _center_distance_on_smaller(det_a.box, det_b.box)
        return (
            overlap_small >= 0.75
            and dist <= self._merge_center_distance_ratio
        )

    def _merge_cluster(
        self,
        cluster: list[Detection],
        frame_shape: tuple[int, ...],
        active_classes: list[str],
    ) -> Detection:
        anchor = max(cluster, key=lambda det: det.confidence)
        weights = [max(det.confidence, 0.05) for det in cluster]
        total_weight = sum(weights)

        merged_box = _clamp_box(
            (
                sum(det.box[0] * weight for det, weight in zip(cluster, weights)) / total_weight,
                sum(det.box[1] * weight for det, weight in zip(cluster, weights)) / total_weight,
                sum(det.box[2] * weight for det, weight in zip(cluster, weights)) / total_weight,
                sum(det.box[3] * weight for det, weight in zip(cluster, weights)) / total_weight,
            ),
            frame_shape,
        )

        label_scores: dict[str, float] = {}
        for det in cluster:
            score = det.confidence + self._class_bonus(det.label, active_classes)
            if self._target is not None and det.label == self._target.label:
                score += self._label_stability_bonus
            if self._preferred_label and det.label == self._preferred_label:
                score += self._label_stability_bonus
            label_scores[det.label] = label_scores.get(det.label, 0.0) + score

        merged_label = max(
            label_scores,
            key=lambda label: (label_scores[label], -self._class_rank(label, active_classes)),
        )

        track_votes: dict[int, float] = {}
        for det in cluster:
            if det.track_id is None:
                continue
            track_votes[det.track_id] = track_votes.get(det.track_id, 0.0) + det.confidence

        merged_track_id = (
            max(track_votes, key=track_votes.get)
            if track_votes
            else anchor.track_id
        )
        merged_conf = min(
            0.99,
            anchor.confidence + min(self._consensus_confidence_bonus, 0.03 * (len(cluster) - 1)),
        )
        return Detection(
            label=merged_label,
            confidence=merged_conf,
            box=merged_box,
            track_id=merged_track_id,
        )

    def _pick_candidate(
        self,
        candidates: list[Detection],
        frame_shape: tuple[int, ...],
        active_classes: list[str],
    ) -> tuple[Detection | None, float]:
        scored = [
            (det, self._score_candidate(det, frame_shape, active_classes))
            for det in candidates
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        best, best_score = scored[0]

        if self._target is None:
            return best, best_score

        incumbent = self._best_incumbent_candidate(scored, frame_shape)
        chosen, chosen_score = best, best_score
        if incumbent is not None and incumbent[0] is not best:
            chosen, chosen_score = self._resolve_target_switch(
                best,
                best_score,
                incumbent[0],
                incumbent[1],
                frame_shape,
            )

        if not self._passes_consistency_gate(chosen, frame_shape):
            return None, 0.0
        return chosen, chosen_score

    def _best_incumbent_candidate(
        self,
        scored: list[tuple[Detection, float]],
        frame_shape: tuple[int, ...],
    ) -> tuple[Detection, float] | None:
        for det, score in scored:
            if self._is_incumbent_candidate(det, frame_shape):
                return det, score
        return None

    def _is_incumbent_candidate(
        self,
        det: Detection,
        frame_shape: tuple[int, ...],
    ) -> bool:
        if self._target is None:
            return False

        reference = self._reference_box()
        if reference is None:
            return False

        if self._same_track(det, self._target):
            return True
        if det.label == self._target.label:
            return True
        if self._preferred_label and det.label == self._preferred_label:
            return True

        dist_ratio = _center_distance_ratio(det.box, reference, frame_shape)
        iou = _iou(det.box, reference)
        area_similarity = _ratio_similarity(
            _area(det.box),
            _area(reference),
            self._max_area_ratio,
        )
        return dist_ratio <= (self._distance_limit(reference, frame_shape) * 0.75) and (
            iou >= 0.12 or area_similarity >= 0.45
        )

    def _resolve_target_switch(
        self,
        best: Detection,
        best_score: float,
        incumbent: Detection,
        incumbent_score: float,
        frame_shape: tuple[int, ...],
    ) -> tuple[Detection, float]:
        if self._target is None:
            return best, best_score

        reference = self._reference_box()
        if reference is None:
            return best, best_score

        best_dist = _center_distance_ratio(best.box, reference, frame_shape)
        incumbent_dist = _center_distance_ratio(incumbent.box, reference, frame_shape)
        best_iou = _iou(best.box, reference)
        incumbent_iou = _iou(incumbent.box, reference)

        risky_switch = (
            best.label != self._target.label
            or best.label != incumbent.label
            or best_dist > (incumbent_dist + 0.05)
            or best_iou + 0.08 < incumbent_iou
        )
        if (
            risky_switch
            and best_score < (incumbent_score + self._switch_margin)
            and best.confidence < self._strong_detection_confidence
        ):
            return incumbent, incumbent_score
        return best, best_score

    def _passes_consistency_gate(
        self,
        det: Detection,
        frame_shape: tuple[int, ...],
    ) -> bool:
        if self._target is None:
            return True

        reference = self._reference_box()
        if reference is None:
            return True

        dist_ratio = _center_distance_ratio(det.box, reference, frame_shape)
        area_similarity = _ratio_similarity(
            _area(det.box),
            _area(reference),
            self._max_area_ratio,
        )
        aspect_similarity = _ratio_similarity(
            _aspect_ratio(det.box),
            _aspect_ratio(reference),
            self._max_aspect_ratio,
        )
        high_conf = det.confidence >= self._strong_detection_confidence
        same_label = det.label == self._target.label or (
            self._preferred_label and det.label == self._preferred_label
        )

        if dist_ratio > self._distance_limit(reference, frame_shape):
            return self._same_track(det, self._target) or high_conf

        if area_similarity < 0.15 and aspect_similarity < 0.10:
            return self._same_track(det, self._target) or same_label or high_conf

        return True

    def _score_candidate(
        self,
        det: Detection,
        frame_shape: tuple[int, ...],
        active_classes: list[str],
    ) -> float:
        score = det.confidence + self._class_bonus(det.label, active_classes)

        h, w = frame_shape[:2]
        frame_area = max(1.0, float(h * w))
        score += min(0.12, _area(det.box) / frame_area)

        reference = self._reference_box()
        if reference is None:
            return score

        dist_ratio = _center_distance_ratio(det.box, reference, frame_shape)
        score += max(
            0.0,
            1.0 - (dist_ratio / max(self._distance_limit(reference, frame_shape), 1e-6)),
        )
        score += _iou(det.box, reference) * self._iou_bonus
        score += _ratio_similarity(
            _area(det.box),
            _area(reference),
            self._max_area_ratio,
        ) * self._area_consistency_bonus
        score += _ratio_similarity(
            _aspect_ratio(det.box),
            _aspect_ratio(reference),
            self._max_aspect_ratio,
        ) * self._aspect_consistency_bonus

        if self._target is not None:
            if self._same_track(det, self._target):
                score += self._track_id_bonus
            if det.label == self._target.label:
                score += self._label_stability_bonus
            elif self._preferred_label and det.label == self._preferred_label:
                score += self._label_stability_bonus * 0.9
            else:
                score -= 0.08

        return score

    def _class_bonus(self, label: str, active_classes: list[str]) -> float:
        rank = self._class_rank(label, active_classes)
        if rank == 0:
            return self._primary_label_bonus
        if rank >= len(active_classes):
            return 0.0
        return max(0.0, self._support_label_bonus - (0.03 * max(0, rank - 1)))

    @staticmethod
    def _class_rank(label: str, active_classes: list[str]) -> int:
        try:
            return active_classes.index(label)
        except ValueError:
            return len(active_classes) + 100

    def _distance_limit(
        self,
        reference: tuple[int, int, int, int],
        frame_shape: tuple[int, ...],
    ) -> float:
        h, w = frame_shape[:2]
        frame_diag = max(1.0, hypot(w, h))
        size_ratio = _box_diag(reference) / frame_diag
        limit = self._max_center_distance_ratio + min(0.12, size_ratio * 0.6)
        if self._status == "acquiring":
            limit *= 1.15
        elif self._status == "lost":
            limit *= 1.8
        return limit

    def _on_hit(
        self,
        det: Detection,
        frame_shape: tuple[int, ...],
        score: float,
    ) -> FollowState:
        previous_target = self._target
        previous_missed = self._missed

        new_box = tuple(int(v) for v in det.box)
        if self._smoothed_box is None:
            smoothed = new_box
            velocity = (0.0, 0.0, 0.0, 0.0)
        else:
            prev = self._smoothed_box
            smoothed = tuple(
                int(round((1.0 - self._alpha) * prev[idx] + self._alpha * new_box[idx]))
                for idx in range(4)
            )
            delta = tuple(float(smoothed[idx] - prev[idx]) for idx in range(4))
            velocity = tuple(
                (0.4 * self._velocity[idx]) + (0.6 * delta[idx])
                for idx in range(4)
            )

        self._target = det
        if not self._preferred_label:
            self._preferred_label = det.label
        elif previous_target is not None and self._same_track(det, previous_target):
            self._preferred_label = det.label
        elif previous_missed == 0 and self._hits < self._acquire_hits:
            self._preferred_label = det.label

        self._smoothed_box = _clamp_box(smoothed, frame_shape)
        self._velocity = velocity
        self._predicted_box = _clamp_box(
            tuple(self._smoothed_box[idx] + self._velocity[idx] for idx in range(4)),
            frame_shape,
        )
        self._hits += 1
        self._missed = 0
        self._score = score
        self._status = "locked" if self._hits >= self._acquire_hits else "acquiring"
        message = (
            f"Target locked after {self._hits} hits."
            if self._status == "locked" and self._hits == self._acquire_hits
            else f"Tracking target ({self._status})."
        )
        return self._state(message=message, use_predicted=False)

    def _on_miss(self, frame_shape: tuple[int, ...]) -> FollowState:
        if self._target is None:
            return FollowState(status="idle", message="No target locked.")

        self._missed += 1
        self._hits = max(0, self._hits - 1)
        if self._predicted_box is not None:
            drifted = tuple(
                self._predicted_box[idx] + self._velocity[idx]
                for idx in range(4)
            )
            self._predicted_box = _clamp_box(drifted, frame_shape)

        if self._missed > self._max_missed:
            last_label = self._preferred_label or self._target.label
            self.reset()
            return FollowState(status="idle", message=f"Lost target: {last_label}.")

        self._status = "lost"
        return self._state(
            message=f"Target temporarily lost ({self._missed}/{self._max_missed}).",
            use_predicted=True,
        )

    def _state(self, message: str, use_predicted: bool) -> FollowState:
        box = self._predicted_box if use_predicted else self._smoothed_box
        return FollowState(
            status=self._status,
            target=self._target,
            display_box=_as_int_box(box),
            predicted_box=_as_int_box(self._predicted_box),
            hits=self._hits,
            missed_frames=self._missed,
            score=self._score,
            message=message,
            search_mode=self._last_search_plan.mode,
            search_box=_as_int_box(self._last_search_plan.roi_box),
            search_reason=self._last_search_plan.reason,
        )

    def _reference_box(self) -> tuple[int, int, int, int] | None:
        return _as_int_box(self._predicted_box or self._smoothed_box)

    def _build_search_box(
        self,
        frame_shape: tuple[int, ...],
        lost: bool,
    ) -> tuple[int, int, int, int] | None:
        reference = self._reference_box()
        if reference is None:
            return None

        h, w = frame_shape[:2]
        cx, cy = _center(reference)
        box_w = max(1.0, float(reference[2] - reference[0]))
        box_h = max(1.0, float(reference[3] - reference[1]))
        padding = self._lost_roi_padding_ratio if lost else self._roi_padding_ratio
        half_w = max(self._roi_min_size / 2.0, box_w * (0.5 + padding))
        half_h = max(self._roi_min_size / 2.0, box_h * (0.5 + padding))
        max_half_w = max(self._roi_min_size / 2.0, (w * self._roi_max_size_ratio) / 2.0)
        max_half_h = max(self._roi_min_size / 2.0, (h * self._roi_max_size_ratio) / 2.0)
        half_w = min(half_w, max_half_w)
        half_h = min(half_h, max_half_h)

        return _clamp_box(
            (cx - half_w, cy - half_h, cx + half_w, cy + half_h),
            frame_shape,
        )

    @staticmethod
    def _same_track(a: Detection, b: Detection) -> bool:
        return a.track_id is not None and b.track_id is not None and a.track_id == b.track_id


def _area(box: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = box
    return max(0.0, float(x2 - x1)) * max(0.0, float(y2 - y1))


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return (0.5 * (x1 + x2), 0.5 * (y1 + y2))


def _box_diag(box: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = box
    return hypot(max(0.0, x2 - x1), max(0.0, y2 - y1))


def _aspect_ratio(box: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = box
    width = max(1.0, float(x2 - x1))
    height = max(1.0, float(y2 - y1))
    return width / height


def _center_distance_ratio(
    box_a: tuple[int, int, int, int],
    box_b: tuple[int, int, int, int],
    frame_shape: tuple[int, ...],
) -> float:
    h, w = frame_shape[:2]
    diag = max(1.0, hypot(w, h))
    ax, ay = _center(box_a)
    bx, by = _center(box_b)
    return hypot(ax - bx, ay - by) / diag


def _center_distance_on_smaller(
    box_a: tuple[int, int, int, int],
    box_b: tuple[int, int, int, int],
) -> float:
    ax, ay = _center(box_a)
    bx, by = _center(box_b)
    scale = max(1.0, min(_box_diag(box_a), _box_diag(box_b)))
    return hypot(ax - bx, ay - by) / scale


def _ratio_similarity(value_a: float, value_b: float, max_ratio: float) -> float:
    if value_a <= 0.0 or value_b <= 0.0:
        return 0.0
    ratio = max(value_a, value_b) / min(value_a, value_b)
    if ratio >= max_ratio:
        return 0.0
    return 1.0 - ((ratio - 1.0) / max(max_ratio - 1.0, 1e-6))


def _overlap_on_smaller(
    box_a: tuple[int, int, int, int],
    box_b: tuple[int, int, int, int],
) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = _area((ix1, iy1, ix2, iy2))
    if inter <= 0.0:
        return 0.0
    return inter / max(1.0, min(_area(box_a), _area(box_b)))


def _iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = _area((ix1, iy1, ix2, iy2))
    if inter <= 0.0:
        return 0.0
    union = _area(box_a) + _area(box_b) - inter
    return inter / union if union > 0.0 else 0.0


def _clamp_box(
    box: tuple[float, float, float, float] | tuple[int, int, int, int],
    frame_shape: tuple[int, ...],
) -> tuple[int, int, int, int]:
    h, w = frame_shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    x1 = max(0, min(w - 1, x1))
    x2 = max(0, min(w - 1, x2))
    y1 = max(0, min(h - 1, y1))
    y2 = max(0, min(h - 1, y2))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def _as_int_box(box: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    if box is None:
        return None
    return tuple(int(v) for v in box)
