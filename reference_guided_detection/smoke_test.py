from __future__ import annotations

from pathlib import Path

import cv2
import gradio as gr
import yaml

import gradio_app
from base import VLMBase
from main import load_config


ROOT = Path(__file__).resolve().parent


class StubVLM(VLMBase):
    def describe(
        self,
        image_path,
        instruction: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        return "red square, blue circle, black text, white background"


def main() -> None:
    config = load_config(ROOT / "config.yaml")
    sample_path = ROOT / "tmp_ref.png"
    sample = cv2.imread(str(sample_path))
    if sample is None:
        raise FileNotFoundError(f"Missing smoke-test image: {sample_path}")

    gradio_app.CONFIG["detector"]["imgsz"] = 320
    gradio_app.VLM = StubVLM(config["vlm"])
    gradio_app.DETECTOR = None

    chat, state, active_reference, _, main_object, refinements, joined, raw, status = (
        gradio_app._update_classes(
            str(sample_path),
            {"text": "detect the main object with simple labels", "files": []},
            gradio_app._empty_state(),
        )
    )
    if status:
        raise RuntimeError(f"Class update failed: {status}")
    if active_reference != str(sample_path):
        raise RuntimeError("Reference image state was not preserved.")
    if not state["classes"] or main_object != "red square":
        raise RuntimeError("Smoke test expected the stub VLM classes to be applied.")
    if "blue circle" not in joined or "white background" not in raw:
        raise RuntimeError("Smoke test expected joined/raw text from the stub VLM.")

    gr.Chatbot().postprocess(chat)

    annotated, summary = gradio_app._detect_target(str(sample_path), state)
    if annotated is None or not summary:
        raise RuntimeError("Target detection did not return an annotated frame and summary.")

    demo = gradio_app.build_demo()
    if demo is None:
        raise RuntimeError("Failed to build the Gradio demo.")

    print("Smoke test passed.")
    print(f"Reference classes: {state['classes']}")
    print(f"Main object: {main_object}")
    print(f"Refinements: {refinements or '(none)'}")
    print(summary)


if __name__ == "__main__":
    main()
