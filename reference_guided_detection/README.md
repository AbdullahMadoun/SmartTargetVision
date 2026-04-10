# Reference-Guided Detection

This folder contains the original reference-image pipeline. A vision-language model reads a single reference image, returns short detector labels, and the detector updates live video using those labels.

```text
reference image -> VLM -> detector labels -> YOLO-World or YOLOE -> live detections
```

## What Is In This Folder

- `main.py`
  CLI entrypoint for the OpenCV live loop.
- `gradio_app.py`
  Browser UI with reference upload, prompt refinement, and live webcam overlay.
- `config.yaml`
  Runtime configuration.
- `smoke_test.py`
  Offline smoke test that stubs the VLM and verifies the moved app still builds and detects.
- `detector/`
  Detector factory plus the YOLO-World and YOLOE backends.
- `utils/`
  Camera, overlay, and target-following helpers.
- `vlm/`
  OpenRouter and local VLM adapters.

## Run

Install dependencies:

```powershell
python -m pip install -r reference_guided_detection/requirements.txt
```

Run the OpenCV live app:

```powershell
python reference_guided_detection/main.py --image reference_guided_detection/tmp_ref.png
```

Run the browser UI:

```powershell
python reference_guided_detection/gradio_app.py
```

If you want the UI to call OpenRouter, set `OPENROUTER_API_KEY` in your environment or `.env` first.

## Smoke Test

Run this before pushing changes:

```powershell
python reference_guided_detection/smoke_test.py
```

What it checks:

- config still loads from the moved folder
- the Gradio app still builds
- chat messages are still valid for Gradio's messages format
- the detector still loads and runs on the bundled sample image
- the reference-label update path still works without a live API call

## Notes

- `main.py` now resolves `config.yaml` relative to this folder, so running it from the repo root does not break.
- `gradio_app.py` now loads its config lazily and only constructs the VLM on demand.
- detector weights are resolved relative to this folder, not the current shell directory.
