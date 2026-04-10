from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import yaml

from drone_identity.engine import (
    IdentityEngine,
    _crop,
    _expand_box,
    _map_box_between_frames,
    _resize_for_detector,
)


ROOT = Path(__file__).resolve().parent


def main() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    engine = IdentityEngine(config=config, root_dir=ROOT)

    sample_path = ROOT / "zidane.jpg"
    sample = cv2.imread(str(sample_path))
    if sample is None:
        raise FileNotFoundError(f"Missing sample image: {sample_path}")

    detector_frame = _resize_for_detector(
        sample,
        int(config.get("runtime", {}).get("reference_detect_max_side", 960)),
    )
    detections = engine._detector.detect(detector_frame)
    if len(detections) < 2:
        raise RuntimeError("Smoke test expects at least two faces in zidane.jpg.")

    first_face = max(detections, key=lambda item: item.confidence)
    scale_box = _map_box_between_frames(
        first_face.box,
        detector_frame.shape[:2],
        sample.shape[:2],
    )
    crop_box = _expand_box(scale_box, sample.shape[:2])
    face_crop = _crop(sample, crop_box)
    if face_crop.size == 0:
        raise RuntimeError("Failed to build a usable enrollment crop.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        reference_path = Path(tmp_dir) / "reference_face.jpg"
        cv2.imwrite(str(reference_path), face_crop)

        profile = engine.create_target_profile([str(reference_path)])
        analysis = engine.analyze_image(str(sample_path), profile.enrollment)

    if len(analysis.matches) < 2:
        raise RuntimeError("Smoke test expected multiple face matches.")
    if not any(item.is_match for item in analysis.matches):
        raise RuntimeError("Smoke test expected at least one MATCH.")
    if not any(not item.is_match for item in analysis.matches):
        raise RuntimeError("Smoke test expected at least one NO MATCH.")

    print("Smoke test passed.")
    print(profile.summary_text)
    print(analysis.summary_text)


if __name__ == "__main__":
    main()
