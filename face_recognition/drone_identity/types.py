from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PromptPlan:
    classes: list[str] = field(default_factory=list)
    raw_vlm: str = ""
    main_class: str = ""
    support_classes: list[str] = field(default_factory=list)
    instruction: str = ""
    source: str = "fallback"


@dataclass
class Detection:
    label: str
    confidence: float
    box: tuple[int, int, int, int]


@dataclass
class Enrollment:
    embedding: np.ndarray
    reference_paths: list[str]
    classes: list[str]
    raw_vlm: str
    prompt_plan: PromptPlan | None = None

    @property
    def main_class(self) -> str:
        if self.prompt_plan and self.prompt_plan.main_class:
            return self.prompt_plan.main_class
        return self.classes[0] if self.classes else ""

    @property
    def support_classes(self) -> list[str]:
        if self.prompt_plan:
            return list(self.prompt_plan.support_classes)
        return list(self.classes[1:])


@dataclass
class MatchResult:
    detection: Detection
    similarity: float
    smoothed_similarity: float
    is_match: bool
    face_box: tuple[int, int, int, int] | None = None
    face_confidence: float | None = None
    note: str = ""


@dataclass
class EnrollmentResult:
    enrollment: Enrollment
    classes: list[str]
    raw_vlm: str
    summary_text: str


@dataclass
class FrameAnalysis:
    detections: list[Detection] = field(default_factory=list)
    matches: list[MatchResult] = field(default_factory=list)
    classes_used: list[str] = field(default_factory=list)
    summary_text: str = ""
    best_match: MatchResult | None = None


@dataclass
class ImageRunResult:
    annotated_rgb: np.ndarray
    matches: list[MatchResult] = field(default_factory=list)
    summary_text: str = ""
