# Live Face Recognition

This folder is the separate multi-face verification approach. It does not depend on the reference-guided detection app.

The live pipeline is:

1. A small YOLO face detector runs on a reduced-resolution frame for speed.
2. Each detected face box is mapped back onto the original source frame.
3. The full-resolution face crop is sent to FaceNet.
4. Cosine similarity scores each face against the enrolled target.
5. The UI labels every face independently as `MATCH` or `NO MATCH`.

## Current Stack

- Detector: `yolov8n-face-lindevs.pt`
- Detector mode: face-only
- Embedder: `facenet-pytorch`
- Face model: `InceptionResnetV1(pretrained='vggface2')`
- Matcher: cosine similarity with temporal smoothing
- UI: Gradio

## Layout

```text
face_recognition/
├── app.py
├── config.yaml
├── requirements.txt
├── smoke_test.py
├── yolov8n-face-lindevs.pt
├── zidane.jpg
└── drone_identity/
    ├── detector.py
    ├── embedder.py
    ├── engine.py
    ├── matcher.py
    ├── pipeline.py
    ├── prompting.py
    ├── types.py
    └── visualize.py
```

## Run

```powershell
python -m pip install -r face_recognition/requirements.txt
python face_recognition/app.py
```

Default port is `7862`, configured in `face_recognition/config.yaml`.

## Smoke Test

```powershell
python face_recognition/smoke_test.py
```

The smoke test verifies:

- the sample image loads
- the detector finds multiple faces
- enrollment succeeds from a detected face crop
- at least one face returns `MATCH`
- at least one face returns `NO MATCH`

## Configuration Notes

Important fields in `face_recognition/config.yaml`:

- `detector.imgsz`
  YOLO face-detector input size.
- `runtime.live_max_side`
  Detector frame size for live webcam inference.
- `runtime.probe_max_side`
  Detector frame size for still-image checks.
- `runtime.reference_detect_max_side`
  Detector frame size for enrollment images.
- `matching.threshold`
  Cosine threshold for `MATCH`.
- `matching.max_candidates_per_frame`
  Maximum number of faces scored per frame.

## Current Behavior

- detection is face-only
- cosine similarity is computed only from detected face crops
- embedding crops come from the higher-resolution source frame
- the overlay is drawn on the lower-resolution detector frame
- each face gets its own independent decision
