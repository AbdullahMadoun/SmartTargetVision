"""
gradio_app.py
Browser UI for reference-image prompting and YOLO-World detection.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import gradio as gr
import yaml

from detector import build_detector
from detector.base import DetectionResult
from utils.display import Renderer
from utils.tracking import TargetFollower
from vlm import build_vlm

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent

with open(ROOT / "config.yaml", "r", encoding="utf-8") as fh:
    CONFIG = yaml.safe_load(fh)

VLM = None
RENDERER = Renderer(config=CONFIG["display"])
VLM_LOCK = threading.Lock()
DETECTOR_LOCK = threading.Lock()
FOLLOWER = TargetFollower(CONFIG.get("tracking", {}))
FOLLOWER_LOCK = threading.Lock()
TRACKING_ENABLED = FOLLOWER.enabled
LIVE_FRAME_INDEX = 0
DETECTOR = None

DEFAULT_INSTRUCTION = (
    "Analyze the reference image and choose concise YOLO-World-friendly labels for the "
    "main objects a detector should look for."
)

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Manrope:wght@400;500;600;700&display=swap');

:root {
  --bg-0: #f5efe3;
  --bg-1: #f9f5ec;
  --panel: rgba(255, 251, 244, 0.9);
  --panel-strong: rgba(255, 248, 236, 0.98);
  --ink: #1f2a21;
  --muted: #5f6b60;
  --accent: #c8642f;
  --accent-2: #2f7f6b;
  --line: rgba(60, 72, 62, 0.12);
  --shadow: 0 24px 60px rgba(76, 59, 34, 0.12);
}

.gradio-container {
  background:
    radial-gradient(circle at top left, rgba(230, 159, 90, 0.18), transparent 30%),
    radial-gradient(circle at top right, rgba(69, 129, 109, 0.16), transparent 28%),
    linear-gradient(180deg, var(--bg-0), var(--bg-1));
  color: var(--ink);
  font-family: 'Manrope', sans-serif;
}

.app-shell {
  max-width: 1500px;
  margin: 0 auto;
  padding: 18px 8px 28px 8px;
}

.hero {
  border: 1px solid var(--line);
  border-radius: 28px;
  padding: 26px 30px;
  background: linear-gradient(135deg, rgba(255, 248, 238, 0.97), rgba(244, 235, 220, 0.94));
  box-shadow: var(--shadow);
  margin-bottom: 18px;
}

.hero h1 {
  margin: 0;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 2.2rem;
  line-height: 1.05;
  letter-spacing: -0.04em;
}

.hero p {
  margin: 10px 0 0 0;
  max-width: 920px;
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
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid var(--line);
}

.panel-card {
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 16px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.panel-card.tight {
  padding-top: 10px;
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

.live-stack {
  gap: 14px;
}

.gr-button-primary {
  background: linear-gradient(135deg, var(--accent), #d88643) !important;
  border: none !important;
}

.gr-button-secondary {
  background: linear-gradient(135deg, var(--accent-2), #44947f) !important;
  border: none !important;
  color: white !important;
}
"""


def _empty_state() -> dict:
    return {
        "history": [],
        "chat": [],
        "classes": [],
        "generated_classes": [],
        "main_object": "",
        "yolo_refinements": "",
        "raw": "",
        "reference_image": None,
    }


def _chat_reply(raw: str, classes: list[str]) -> str:
    classes_text = ", ".join(classes) if classes else "(no classes)"
    return f"Detector classes updated:\n{classes_text}\n\nRaw VLM output:\n{raw}"


def _chat_messages(
    user_text: str,
    reply_text: str,
    chat: list[dict] | None,
    image_path: str | None = None,
) -> list[dict]:
    messages = list(chat or [])
    prompt_text = user_text
    if image_path:
        prompt_text = f"[image uploaded] {user_text}".strip()
    messages.append({"role": "user", "content": prompt_text})
    messages.append({"role": "assistant", "content": reply_text})
    return messages[-12:]


def _parse_label_text(raw: str) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        label = str(item).strip().lower().strip(" '\"`.;:!?")
        if label and label not in seen:
            seen.add(label)
            cleaned.append(label)
    return cleaned


def _reset_live_tracking() -> None:
    global LIVE_FRAME_INDEX
    with DETECTOR_LOCK:
        if DETECTOR is not None:
            DETECTOR.reset_tracking()
    with FOLLOWER_LOCK:
        FOLLOWER.reset()
    LIVE_FRAME_INDEX = 0


def _summarize_detections(result, follow_state=None) -> str:
    header_lines = []
    if follow_state:
        header_lines.append(
            f"Search {follow_state.search_mode}: {follow_state.search_reason or '-'}"
        )
        if follow_state.target:
            target = follow_state.target
            track = f" #{target.track_id}" if target.track_id is not None else ""
            header_lines.append(
                (
                    f"Target {follow_state.status}: {target.label}{track} | "
                    f"hits={follow_state.hits} | missed={follow_state.missed_frames}"
                )
            )
        elif follow_state.message:
            header_lines.append(f"Target {follow_state.status}: {follow_state.message}")

    if not result.detections:
        body = f"No detections. Inference: {result.inference_ms:.0f} ms"
        return ("\n".join(header_lines) + "\n\n" if header_lines else "") + body

    rows = [
        (
            f"{det.label} ({det.confidence:.0%})"
            f"{f' #{det.track_id}' if det.track_id is not None else ''} @ {det.box}"
        )
        for det in result.detections
    ]
    body = (
        f"{len(result.detections)} detections. "
        f"Inference: {result.inference_ms:.0f} ms\n\n" + "\n".join(rows)
    )
    return ("\n".join(header_lines) + "\n\n" if header_lines else "") + body


def _run_detection_on_bgr(frame_bgr, classes: list[str], track: bool = False):
    with DETECTOR_LOCK:
        detector = _get_detector()
        detector.set_classes(classes)
        return detector.detect(frame_bgr, track=track)


def _run_detection_on_roi(
    frame_bgr,
    classes: list[str],
    roi_box: tuple[int, int, int, int],
    track: bool = False,
):
    with DETECTOR_LOCK:
        detector = _get_detector()
        detector.set_classes(classes)
        return detector.detect_in_roi(frame_bgr, roi_box, track=track)


def _get_detector():
    global DETECTOR
    if DETECTOR is None:
        DETECTOR = build_detector(CONFIG["detector"])
    return DETECTOR


def _get_vlm():
    global VLM
    if VLM is None:
        VLM = build_vlm(CONFIG["vlm"])
    return VLM


def _build_active_classes(main_object: str, refinement_text: str) -> list[str]:
    merged = []
    raw_items = [main_object] + refinement_text.split(",")
    for item in raw_items:
        parsed = _parse_label_text(item)
        label = parsed[0] if parsed else ""
        if label and label not in merged:
            merged.append(label)
    return merged


def _format_class_outputs(classes: list[str]) -> tuple[str, str, str]:
    main_object = classes[0] if classes else ""
    refinements = ", ".join(classes[1:]) if len(classes) > 1 else ""
    joined = ", ".join(classes)
    return main_object, refinements, joined


def _extract_chat_input(chat_input) -> tuple[str, str | None]:
    if not chat_input:
        return "", None
    text = (chat_input.get("text") or "").strip()
    files = chat_input.get("files") or []
    image_path = None
    if files:
        first = files[0]
        image_path = first if isinstance(first, str) else first.get("path")
    return text, image_path


def _update_classes(reference_image: str, chat_input, state: dict | None):
    state = dict(state or _empty_state())
    message, uploaded_image = _extract_chat_input(chat_input)
    active_reference = uploaded_image or reference_image or state.get("reference_image")
    if not active_reference:
        return (
            state.get("chat", []),
            state,
            None,
            None,
            "",
            "",
            "",
            "",
            "Upload or capture a reference image first.",
        )

    instruction = message or DEFAULT_INSTRUCTION
    user_text = instruction
    vlm = _get_vlm()

    try:
        with VLM_LOCK:
            raw = vlm.describe(
                Path(active_reference),
                instruction=instruction,
                history=state.get("history", []),
            )
            classes = vlm.parse_classes(raw)
    except Exception as exc:
        log.exception("VLM update failed")
        return (
            state.get("chat", []),
            state,
            active_reference,
            gr.update(value=None),
            state.get("main_object", ""),
            state.get("yolo_refinements", ""),
            "",
            "",
            f"VLM request failed: {exc}",
        )

    main_object, refinements, joined = _format_class_outputs(classes)
    state["history"] = (state.get("history", []) + [
        {"role": "user", "content": instruction},
        {"role": "assistant", "content": raw},
    ])[-8:]
    reply_text = _chat_reply(raw, classes)
    state["chat"] = _chat_messages(
        user_text,
        reply_text,
        state.get("chat"),
        image_path=uploaded_image,
    )
    state["generated_classes"] = classes
    state["main_object"] = main_object
    state["yolo_refinements"] = refinements
    state["classes"] = _build_active_classes(main_object, refinements)
    state["raw"] = raw
    state["reference_image"] = active_reference
    _reset_live_tracking()

    return (
        state["chat"],
        state,
        active_reference,
        gr.update(value=None),
        main_object,
        refinements,
        joined,
        raw,
        "",
    )


def _apply_yolo_refinements(main_object: str, refinement_text: str, state: dict | None):
    state = dict(state or _empty_state())
    classes = _build_active_classes(main_object or "", refinement_text or "")
    state["main_object"] = classes[0] if classes else ""
    state["yolo_refinements"] = ", ".join(classes[1:]) if len(classes) > 1 else ""
    state["classes"] = classes
    _reset_live_tracking()
    status = (
        f"Applied {len(classes)} YOLO class(es)."
        if classes
        else "Set a main object or refinement label first."
    )
    return (
        state,
        state["main_object"],
        state["yolo_refinements"],
        ", ".join(classes),
        status,
    )


def _detect_target(target_image: str, state: dict | None):
    state = dict(state or _empty_state())
    if not target_image:
        return None, "Upload or capture a target image to run detection."

    classes = state.get("classes", [])
    if not classes:
        return None, "Generate detector classes from a reference image first."

    frame = cv2.imread(str(target_image))
    if frame is None:
        return None, "Failed to read the target image."

    try:
        result = _run_detection_on_bgr(frame, classes, track=False)
    except Exception as exc:
        log.exception("Detection failed")
        return None, f"Detection failed: {exc}"

    annotated = RENDERER.draw(frame.copy(), result, classes, 0.0, follow_state=None)
    annotated = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    return annotated, _summarize_detections(result)


def _detect_live_frame(live_frame, state: dict | None):
    global LIVE_FRAME_INDEX
    if live_frame is None:
        return None, "Enable the webcam to start live detection."

    state = dict(state or _empty_state())
    classes = state.get("classes", [])
    frame_rgb = live_frame.copy()
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    if not classes:
        cv2.putText(
            frame_rgb,
            "Set a reference image and chat prompt first",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 180, 60),
            2,
            cv2.LINE_AA,
        )
        return frame_rgb, "Generate YOLO classes from a reference image first."

    LIVE_FRAME_INDEX += 1
    with FOLLOWER_LOCK:
        search_plan = FOLLOWER.plan_search(frame_bgr.shape, LIVE_FRAME_INDEX)

    try:
        if search_plan.mode == "roi" and search_plan.roi_box:
            result = _run_detection_on_roi(
                frame_bgr,
                classes,
                search_plan.roi_box,
                track=False,
            )
        else:
            result = _run_detection_on_bgr(
                frame_bgr,
                classes,
                track=TRACKING_ENABLED,
            )
    except Exception as exc:
        log.exception("Live detection failed")
        return frame_rgb, f"Live detection failed: {exc}"

    follow_state = None
    if TRACKING_ENABLED:
        with FOLLOWER_LOCK:
            refined = FOLLOWER.refine_detections(result.detections, frame_bgr.shape, classes)
            result = DetectionResult(detections=refined, inference_ms=result.inference_ms)
            follow_state = FOLLOWER.update(
                result.detections,
                frame_bgr.shape,
                classes,
                prepared=True,
            )

    annotated = RENDERER.draw(
        frame_bgr.copy(),
        result,
        classes,
        0.0,
        follow_state=follow_state,
    )
    return cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB), _summarize_detections(
        result,
        follow_state=follow_state,
    )


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="VLM to YOLO-World") as demo:
        state = gr.State(_empty_state())

        with gr.Column(elem_classes=["app-shell"]):
            gr.HTML(
                """
                <section class="hero">
                  <h1>Reference-guided live YOLO-World detection</h1>
                  <p>
                    Drop or capture a reference image, tell the VLM what the main target is,
                    tune the final YOLO labels if needed, and watch the live webcam stream update
                    with overlaid detections in the same app.
                  </p>
                  <div class="pill-row">
                    <span class="pill">1. Send prompt to VLM</span>
                    <span class="pill">2. Confirm main object</span>
                    <span class="pill">3. Refine YOLO labels</span>
                    <span class="pill">4. Run live webcam detection</span>
                  </div>
                </section>
                """
            )

            with gr.Row(equal_height=True):
                with gr.Column(scale=4):
                    with gr.Group(elem_classes=["panel-card"]):
                        gr.HTML(
                            """
                            <h3 class="section-header">Reference and prompt</h3>
                            <p class="section-copy">
                              Use a clean reference image of the main target. You can also drop a new image
                              directly into the prompt box to replace the current reference during chat.
                            </p>
                            """
                        )
                        reference_image = gr.Image(
                            label="Reference Target",
                            type="filepath",
                            sources=["upload", "webcam"],
                        )
                        prompt = gr.MultimodalTextbox(
                            label="Prompt to VLM",
                            placeholder=(
                                "Example: detect the main object in this image, keep the labels simple, "
                                "focus on the most stable visual cues."
                            ),
                            file_types=["image"],
                        )
                        with gr.Row():
                            update_btn = gr.Button("Send to VLM", variant="primary")
                            clear_btn = gr.Button("Reset")

                    with gr.Group(elem_classes=["panel-card", "tight"]):
                        gr.HTML(
                            """
                            <h3 class="section-header">YOLO label tuning</h3>
                            <p class="section-copy">
                              The first field is the primary target. Use refinements for short backup labels
                              you want YOLO-World to search for during live video.
                            </p>
                            """
                        )
                        main_object_box = gr.Textbox(
                            label="Main Object",
                            placeholder="Primary thing YOLO should detect",
                            lines=1,
                        )
                        refinement_box = gr.Textbox(
                            label="YOLO Refinements",
                            placeholder="Extra simple YOLO labels, comma-separated",
                            lines=2,
                        )
                        with gr.Row():
                            apply_btn = gr.Button("Apply YOLO Labels", variant="secondary")
                        classes_box = gr.Textbox(label="Active YOLO Classes", lines=4)
                        status_box = gr.Textbox(label="Status", lines=2)

                    with gr.Group(elem_classes=["panel-card"]):
                        gr.HTML(
                            """
                            <h3 class="section-header">VLM reasoning</h3>
                            <p class="section-copy">
                              Review the chat turns and raw detector-friendly output that the VLM produced.
                            </p>
                            """
                        )
                        chatbot = gr.Chatbot(label="VLM Chat", height=300)
                        raw_box = gr.Textbox(label="Raw VLM Output", lines=5)

                    with gr.Accordion("Still image check", open=False):
                        test_image = gr.Image(
                            label="Optional Test Image",
                            type="filepath",
                            sources=["upload", "webcam"],
                        )
                        test_output = gr.Image(label="Test Image Detection")
                        test_summary = gr.Textbox(label="Test Image Summary", lines=8)

                with gr.Column(scale=6, elem_classes=["live-stack"]):
                    with gr.Group(elem_classes=["panel-card"]):
                        gr.HTML(
                            """
                            <h3 class="section-header">Live video detection</h3>
                            <p class="section-copy">
                              Start the browser webcam here. Every streamed frame is sent through YOLO-World and
                              the follower keeps a soft lock on the best matching moving target.
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
                            detected_image = gr.Image(label="YOLO-World Overlay Output")
                        detection_box = gr.Textbox(label="Live Detection Summary", lines=10)

        update_event = update_btn.click(
            _update_classes,
            inputs=[reference_image, prompt, state],
            outputs=[
                chatbot,
                state,
                reference_image,
                prompt,
                main_object_box,
                refinement_box,
                classes_box,
                raw_box,
                status_box,
            ],
        )
        prompt.submit(
            _update_classes,
            inputs=[reference_image, prompt, state],
            outputs=[
                chatbot,
                state,
                reference_image,
                prompt,
                main_object_box,
                refinement_box,
                classes_box,
                raw_box,
                status_box,
            ],
        ).then(
            _detect_target,
            inputs=[test_image, state],
            outputs=[test_output, test_summary],
        )
        apply_btn.click(
            _apply_yolo_refinements,
            inputs=[main_object_box, refinement_box, state],
            outputs=[state, main_object_box, refinement_box, classes_box, status_box],
        ).then(
            _detect_target,
            inputs=[test_image, state],
            outputs=[test_output, test_summary],
        )
        update_event.then(
            _detect_target,
            inputs=[test_image, state],
            outputs=[test_output, test_summary],
        )
        test_image.change(
            _detect_target,
            inputs=[test_image, state],
            outputs=[test_output, test_summary],
        )
        live_camera.stream(
            _detect_live_frame,
            inputs=[live_camera, state],
            outputs=[detected_image, detection_box],
            trigger_mode="always_last",
            concurrency_limit=1,
            queue=False,
        )

        def _clear():
            _reset_live_tracking()
            empty = _empty_state()
            return None, gr.update(value=None), "", "", "", "", [], empty, None, "", "", None, None, ""

        clear_btn.click(
            _clear,
            outputs=[
                reference_image,
                prompt,
                main_object_box,
                refinement_box,
                classes_box,
                status_box,
                chatbot,
                state,
                detected_image,
                detection_box,
                raw_box,
                test_image,
                test_output,
                test_summary,
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
    launch_demo()
