"""
vlm/local.py
Local / self-hosted VLM backend.

Compatible with any OpenAI-compatible server that accepts image_url in
the messages array — this includes:
  · Ollama  (ollama serve, model: llava, bakllava, llava-phi3 …)
  · vLLM    (vllm serve <model> --api-key …)
  · LM Studio
  · Jan.ai

No API key is required by default — set vlm.local.api_key if your server
needs one.
"""

import base64
import logging
from pathlib import Path

import httpx

from vlm.base import VLMBase

log = logging.getLogger(__name__)


class LocalVLM(VLMBase):
    """
    Sends requests to a locally-running OpenAI-compatible VLM server.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        local_cfg = config["local"]
        self._base_url = local_cfg["base_url"].rstrip("/")
        self._model = local_cfg["model"]
        self._max_tokens = local_cfg.get("max_tokens", 512)
        self._timeout = local_cfg.get("timeout", 60)
        self._prompt = config["prompt_template"]

        headers = {"Content-Type": "application/json"}
        api_key = local_cfg.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def describe(
        self,
        image_path: str | Path,
        instruction: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        image_path = Path(image_path)
        b64 = self._encode_image(image_path)
        media_type = _media_type(image_path)
        user_text = (
            instruction.strip()
            if instruction and instruction.strip()
            else (
                "Analyze this reference image and produce the best short noun "
                "phrases for YOLO-World detection."
            )
        )

        messages: list[dict] = [{"role": "system", "content": self._prompt}]
        if history:
            for item in history[-6:]:
                role = item.get("role", "")
                content = item.get("content", "").strip()
                if role in {"user", "assistant", "system"} and content:
                    messages.append({"role": role, "content": content})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{b64}"
                        },
                    },
                ],
            }
        )

        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }

        log.debug("Sending image to local VLM (%s @ %s) …", self._model, self._base_url)
        response = self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()

        raw = response.json()["choices"][0]["message"]["content"].strip()
        log.info("VLM raw output: %s", raw)
        return raw

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _encode_image(path: Path) -> str:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode("utf-8")

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _media_type(path: Path) -> str:
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(
        Path(str(path)).suffix.lower(), "image/jpeg"
    )
