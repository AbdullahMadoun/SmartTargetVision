from __future__ import annotations

import re

from .prompting import PromptGenerator
from .types import PromptPlan


class DetectorPromptPlanner:
    def __init__(self, config: dict, fallback_classes: list[str]) -> None:
        self._generator = PromptGenerator(config)
        self._fallback_classes = _dedupe_labels(fallback_classes)

    def plan_from_reference(
        self,
        reference_path: str,
        instruction: str | None = None,
    ) -> PromptPlan:
        if not self._generator.is_ready():
            return self._fallback_plan(instruction=instruction)

        try:
            raw = self._generator.generate(reference_path, instruction=instruction)
            classes = _dedupe_labels(self._generator.parse_classes(raw))
            if not classes:
                return self._fallback_plan(instruction=instruction, raw_vlm=raw)
            return _plan_from_classes(
                classes=classes,
                raw_vlm=raw,
                instruction=instruction,
                source="vlm",
            )
        except Exception as exc:
            return self._fallback_plan(
                instruction=instruction,
                raw_vlm=f"VLM planning failed, using fallback classes: {exc}",
                source="fallback_error",
            )

    def plan_from_manual_labels(
        self,
        main_label: str = "",
        support_labels: str | list[str] | None = None,
        raw_vlm: str = "",
        instruction: str = "",
        source: str = "manual",
    ) -> PromptPlan:
        labels = _manual_labels(main_label, support_labels)
        if not labels:
            return self._fallback_plan(instruction=instruction, raw_vlm=raw_vlm, source=source)
        return _plan_from_classes(
            classes=labels,
            raw_vlm=raw_vlm,
            instruction=instruction,
            source=source,
        )

    def apply_overrides(
        self,
        prompt_plan: PromptPlan,
        main_label: str = "",
        support_labels: str | list[str] | None = None,
    ) -> PromptPlan:
        labels = _manual_labels(main_label, support_labels)
        if not labels:
            labels = prompt_plan.classes or self._fallback_classes
        return _plan_from_classes(
            classes=labels,
            raw_vlm=prompt_plan.raw_vlm,
            instruction=prompt_plan.instruction,
            source="manual_override" if labels != prompt_plan.classes else prompt_plan.source,
        )

    def _fallback_plan(
        self,
        instruction: str | None = None,
        raw_vlm: str = "",
        source: str = "fallback",
    ) -> PromptPlan:
        return _plan_from_classes(
            classes=list(self._fallback_classes),
            raw_vlm=raw_vlm,
            instruction=instruction or "",
            source=source,
        )


def _plan_from_classes(
    classes: list[str],
    raw_vlm: str,
    instruction: str | None,
    source: str,
) -> PromptPlan:
    deduped = _dedupe_labels(classes)
    main_class = deduped[0] if deduped else ""
    support_classes = deduped[1:]
    return PromptPlan(
        classes=deduped,
        raw_vlm=raw_vlm,
        main_class=main_class,
        support_classes=support_classes,
        instruction=instruction or "",
        source=source,
    )


def _manual_labels(main_label: str, support_labels: str | list[str] | None) -> list[str]:
    labels: list[str] = []
    if main_label:
        labels.extend(_split_labels(main_label))
    if isinstance(support_labels, str):
        labels.extend(_split_labels(support_labels))
    elif support_labels:
        labels.extend(_dedupe_labels(support_labels))
    return _dedupe_labels(labels)


def _split_labels(raw: str) -> list[str]:
    chunks = re.split(r"[,;\n]+", raw)
    return _dedupe_labels(chunks)


def _clean_label(label: str) -> str:
    label = label.strip().lower()
    label = re.sub(r"^[\s\-*\d\.\)\(]+", "", label)
    label = label.strip(" '\"`.;:!?")
    label = re.sub(r"\s+", " ", label)
    return label


def _dedupe_labels(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in labels:
        label = _clean_label(str(item))
        if label and label not in seen:
            seen.add(label)
            cleaned.append(label)
    return cleaned
