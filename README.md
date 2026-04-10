# SmartTargetVision

This repository now keeps the two vision workflows separated and documented as independent approaches:

- `reference_guided_detection/`
  Reference-image prompting with a VLM that generates YOLO-friendly labels for live YOLO-World or YOLOE detection.
- `face_recognition/`
  Live multi-face verification with a small YOLO face detector and FaceNet cosine matching on full-resolution face crops.

## Repository Layout

```text
SmartTargetVision/
├── docs/
│   └── identity_engine_spec.md
├── face_recognition/
│   ├── app.py
│   ├── config.yaml
│   ├── smoke_test.py
│   └── drone_identity/
├── reference_guided_detection/
│   ├── main.py
│   ├── gradio_app.py
│   ├── config.yaml
│   ├── smoke_test.py
│   ├── detector/
│   ├── utils/
│   └── vlm/
└── README.md
```

## Approach 1: Reference-Guided Detection

`reference_guided_detection` is the original reference-driven detection app. A reference image goes to the VLM, the VLM emits short detector labels, and the live detector updates from those labels.

Primary entrypoints:

- `python reference_guided_detection/main.py --image reference_guided_detection/tmp_ref.png`
- `python reference_guided_detection/gradio_app.py`

Verification:

- `python reference_guided_detection/smoke_test.py`

## Approach 2: Live Face Recognition

`face_recognition` is the separate face-verification app. It detects multiple faces live, maps each low-resolution detection back to the original frame, embeds each face crop with FaceNet, and scores each face against the enrolled target with cosine similarity.

Primary entrypoints:

- `python face_recognition/app.py`
- `python face_recognition/smoke_test.py`

## Notes

- The two approaches do not depend on each other at runtime.
- Root-only local artifacts such as `.env`, `mnt/`, and the large `mobileclip_blt.ts` file are ignored for GitHub push hygiene.
- The design notes you used for the identity engine live in `docs/identity_engine_spec.md`.
