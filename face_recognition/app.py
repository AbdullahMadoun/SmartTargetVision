from __future__ import annotations

import logging
from pathlib import Path

import cv2
import gradio as gr
import yaml

try:
    from drone_identity.pipeline import DroneIdentityPipeline
except ImportError:
    from face_recognition.drone_identity.pipeline import DroneIdentityPipeline


ROOT = Path(__file__).resolve().parent

with open(ROOT / "config.yaml", "r", encoding="utf-8") as fh:
    CONFIG = yaml.safe_load(fh)

PIPELINE = DroneIdentityPipeline(config=CONFIG, root_dir=ROOT)

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

:root {
  --bg-0: #eef1f4;
  --bg-1: #f7f8fa;
  --panel: rgba(255, 255, 255, 0.92);
  --ink: #122030;
  --muted: #5f6f80;
  --accent: #c7642e;
  --accent-2: #1f6d8c;
  --line: rgba(25, 45, 65, 0.10);
  --shadow: 0 24px 60px rgba(18, 32, 48, 0.12);
}

.gradio-container {
  background:
    radial-gradient(circle at top left, rgba(199, 100, 46, 0.12), transparent 28%),
    radial-gradient(circle at top right, rgba(31, 109, 140, 0.12), transparent 26%),
    linear-gradient(180deg, var(--bg-0), var(--bg-1));
  color: var(--ink);
  font-family: 'IBM Plex Sans', sans-serif;
}

.app-shell {
  max-width: 1500px;
  margin: 0 auto;
  padding: 18px 10px 28px 10px;
}

.hero {
  border: 1px solid var(--line);
  border-radius: 28px;
  padding: 28px 30px;
  background: linear-gradient(135deg, rgba(255, 252, 247, 0.98), rgba(245, 249, 252, 0.95));
  box-shadow: var(--shadow);
  margin-bottom: 18px;
}

.hero h1 {
  margin: 0;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 2.25rem;
  line-height: 1.04;
  letter-spacing: -0.04em;
}

.hero p {
  margin: 10px 0 0 0;
  max-width: 980px;
  color: var(--muted);
  font-size: 1rem;
}

.pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

.pill {
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 0.9rem;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid var(--line);
}

.panel-card {
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 16px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.section-header {
  margin: 0 0 8px 0;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 1rem;
  letter-spacing: -0.02em;
}

.section-copy {
  margin: 0 0 10px 0;
  color: var(--muted);
  font-size: 0.92rem;
}

.gr-button-primary {
  background: linear-gradient(135deg, var(--accent), #d77b47) !important;
  border: none !important;
}

.gr-button-secondary {
  background: linear-gradient(135deg, var(--accent-2), #2f84a6) !important;
  border: none !important;
  color: white !important;
}
"""


def _empty_state() -> dict:
    return {
        "enrollment": None,
        "reference_paths": [],
    }


def _model_summary() -> str:
    detector_weights = Path(CONFIG["detector"]["weights"]).name
    detector_device = CONFIG["detector"].get("device", "cpu")
    embedder_backend = CONFIG["embedder"].get("backend", "facenet")
    embedder_pretrained = CONFIG["embedder"].get("pretrained", "")
    return (
        f"Detector: YOLO face ({detector_weights}) on {detector_device}\n"
        f"Verifier: {embedder_backend} ({embedder_pretrained})\n"
        f"Decision threshold: {PIPELINE.match_threshold:.2f}"
    )


def _collect_reference_paths(primary_reference, extra_references) -> list[str]:
    paths: list[str] = []
    if primary_reference:
        paths.append(str(Path(primary_reference)))
    for item in extra_references or []:
        path = str(Path(item))
        if path not in paths:
            paths.append(path)
    return paths


def _resize_rgb(frame_rgb, max_side: int):
    if frame_rgb is None:
        return None

    height, width = frame_rgb.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return frame_rgb

    scale = max_side / float(longest)
    return cv2.resize(
        frame_rgb,
        (max(1, int(width * scale)), max(1, int(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def enroll_target(primary_reference, extra_references, state: dict | None):
    state = dict(state or _empty_state())
    reference_paths = _collect_reference_paths(primary_reference, extra_references)
    if not reference_paths:
        state["enrollment"] = None
        state["reference_paths"] = []
        return state, "", "Add at least one clear face reference image.", "Enroll a face first to start live verification."

    PIPELINE.reset_temporal_state()
    try:
        result = PIPELINE.enroll(reference_paths=reference_paths)
    except Exception as exc:
        logging.exception("Enrollment failed")
        state["enrollment"] = None
        state["reference_paths"] = []
        return state, "", f"Enrollment failed: {exc}", "Enrollment failed."

    state["enrollment"] = result.enrollment
    state["reference_paths"] = reference_paths
    live_status = (
        "Reference enrolled. Start the webcam and each detected face will be labeled "
        "MATCH or NO MATCH against the enrolled face."
    )
    return state, result.summary_text, "Enrollment complete.", live_status


def run_probe(target_image, state: dict | None):
    state = dict(state or _empty_state())
    enrollment = state.get("enrollment")
    if not target_image:
        return None, "Upload or capture a probe image."
    if not enrollment:
        return None, "Enroll a reference face first."

    image = cv2.imread(str(Path(target_image)))
    if image is None:
        return None, "Could not read the probe image."
    source_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    probe_rgb = _resize_rgb(
        source_rgb,
        int(CONFIG.get("runtime", {}).get("probe_max_side", 960)),
    )

    try:
        result = PIPELINE.run_on_rgb(
            probe_rgb,
            enrollment,
            source_frame_rgb=source_rgb,
        )
    except Exception as exc:
        logging.exception("Probe failed")
        return None, f"Probe failed: {exc}"
    return result.annotated_rgb, result.summary_text


def run_live_frame(live_frame, state: dict | None):
    if live_frame is None:
        return None, "Enable the webcam to start live verification."

    state = dict(state or _empty_state())
    enrollment = state.get("enrollment")
    source_rgb = live_frame.copy()
    prepared_rgb = _resize_rgb(
        source_rgb,
        int(CONFIG.get("runtime", {}).get("live_max_side", 640)),
    )

    if prepared_rgb is None:
        return None, "Waiting for a webcam frame."

    if not enrollment:
        overlay = prepared_rgb.copy()
        cv2.putText(
            overlay,
            "Enroll a reference face first",
            (14, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (255, 180, 70),
            2,
            cv2.LINE_AA,
        )
        return overlay, "Enroll a reference face first."

    try:
        result = PIPELINE.run_on_rgb(
            prepared_rgb,
            enrollment,
            source_frame_rgb=source_rgb,
        )
    except Exception as exc:
        logging.exception("Live verification failed")
        return prepared_rgb, f"Live verification failed: {exc}"

    return result.annotated_rgb, result.summary_text


def clear_all():
    PIPELINE.reset_temporal_state()
    return (
        None,
        None,
        "",
        "Reset complete.",
        _empty_state(),
        None,
        None,
        "",
        "Enroll a face first to start live verification.",
    )


def build_demo() -> gr.Blocks:
    with gr.Blocks(title=CONFIG["app"]["title"]) as demo:
        state = gr.State(_empty_state())

        with gr.Column(elem_classes=["app-shell"]):
            gr.HTML(
                """
                <section class="hero">
                  <h1>Real-time face recognizer</h1>
                  <p>
                    This app uses a small YOLO face detector to find multiple faces in the frame, then runs
                    FaceNet on each detected face crop and compares every face against the enrolled reference
                    with cosine similarity.
                  </p>
                  <div class="pill-row">
                    <span class="pill">1. Add reference face</span>
                    <span class="pill">2. Enroll target</span>
                    <span class="pill">3. Open webcam</span>
                    <span class="pill">4. Watch MATCH / NO MATCH live</span>
                  </div>
                </section>
                """
            )

            with gr.Row(equal_height=True):
                with gr.Column(scale=4):
                    with gr.Group(elem_classes=["panel-card"]):
                        gr.HTML('<h3 class="section-header">Reference enrollment</h3>')
                        gr.HTML(
                            f'<p class="section-copy">{CONFIG["ui"]["reference_hint"].strip()}</p>'
                        )
                        primary_reference = gr.Image(
                            label="Primary Reference Face",
                            type="filepath",
                            sources=["upload", "webcam"],
                        )
                        extra_references = gr.File(
                            label="Extra Reference Faces",
                            file_count="multiple",
                            file_types=["image"],
                            type="filepath",
                        )
                        with gr.Row():
                            enroll_btn = gr.Button("Enroll Face", variant="primary")
                            clear_btn = gr.Button("Reset", variant="secondary")
                        model_box = gr.Textbox(
                            label="Active Models",
                            lines=3,
                            value=_model_summary(),
                            interactive=False,
                        )
                        enrollment_box = gr.Textbox(
                            label="Enrollment Summary",
                            lines=7,
                            interactive=False,
                        )
                        status_box = gr.Textbox(
                            label="Status",
                            lines=2,
                            interactive=False,
                            value="Add a reference face and enroll it.",
                        )

                    with gr.Accordion("Still image check", open=False):
                        probe_image = gr.Image(
                            label="Probe Image",
                            type="filepath",
                            sources=["upload", "webcam"],
                        )
                        probe_output = gr.Image(label="Probe Overlay")
                        probe_summary = gr.Textbox(
                            label="Probe Summary",
                            lines=8,
                            interactive=False,
                        )

                with gr.Column(scale=6):
                    with gr.Group(elem_classes=["panel-card"]):
                        gr.HTML('<h3 class="section-header">Live webcam verification</h3>')
                        gr.HTML(
                            """
                            <p class="section-copy">
                              The left panel is the browser webcam feed. The right panel shows all detected
                              faces, each with its own live cosine score and MATCH or NO MATCH label.
                            </p>
                            """
                        )
                        with gr.Row(equal_height=True):
                            live_camera = gr.Image(
                                label="Live Camera Input",
                                sources=["webcam"],
                                type="numpy",
                                streaming=True,
                            )
                            live_output = gr.Image(label="Live Overlay Output")
                        live_summary = gr.Textbox(
                            label="Live Verification Summary",
                            lines=10,
                            interactive=False,
                            value="Enroll a face first to start live verification.",
                        )

        enroll_event = enroll_btn.click(
            enroll_target,
            inputs=[primary_reference, extra_references, state],
            outputs=[state, enrollment_box, status_box, live_summary],
        )
        probe_image.change(
            run_probe,
            inputs=[probe_image, state],
            outputs=[probe_output, probe_summary],
        )
        enroll_event.then(
            run_probe,
            inputs=[probe_image, state],
            outputs=[probe_output, probe_summary],
        )
        live_camera.stream(
            run_live_frame,
            inputs=[live_camera, state],
            outputs=[live_output, live_summary],
            trigger_mode="always_last",
            concurrency_limit=1,
            queue=False,
        )
        clear_btn.click(
            clear_all,
            outputs=[
                primary_reference,
                extra_references,
                enrollment_box,
                status_box,
                state,
                live_output,
                probe_output,
                probe_summary,
                live_summary,
            ],
            queue=False,
        )

    return demo


def launch_demo(**kwargs):
    demo = build_demo()
    return demo.launch(css=APP_CSS, **kwargs)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    launch_demo(
        share=bool(CONFIG["app"].get("share", False)),
        server_port=int(CONFIG["app"].get("port", 7860)),
    )
