"""
vlm/openrouter.py
OpenRouter API backend — the primary VLM provider.

Supports any vision-capable model available on openrouter.ai, e.g.:
  · google/gemini-flash-1.5          (fast, cheap, excellent vision)
  · openai/gpt-4o-mini               (solid baseline)
  · anthropic/claude-3-haiku         (good at structured output)
  · meta-llama/llama-3.2-11b-vision-instruct  (open-weight option)

Set OPENROUTER_API_KEY in your environment or in config.yaml.
"""

import base64
import logging
import os
from pathlib import Path

import httpx
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from vlm.base import VLMBase

log = logging.getLogger(__name__)


class OpenRouterVLM(VLMBase):
    """
    Calls the OpenRouter /chat/completions endpoint with a base64-encoded
    image and the configured prompt template, then returns the text response.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        if load_dotenv:
            load_dotenv()
        api_cfg = config["api"]
        self._base_url = api_cfg["base_url"].rstrip("/")
        self._model = api_cfg["model"]
        self._max_tokens = api_cfg.get("max_tokens", 512)
        self._timeout = api_cfg.get("timeout", 30)
        self._prompt = config["prompt_template"]

        # Resolve API key: config → env
        self._api_key = (
            api_cfg.get("api_key")
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OpenRouter_Key")
            or os.environ.get("OPENROUTER_KEY")
        )
        if not self._api_key:
            raise EnvironmentError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY "
                "or set vlm.api.api_key in config.yaml."
            )

        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "HTTP-Referer": "https://github.com/local/vlm-yolo-pipeline",
                "X-Title": "VLM-YOLO-Pipeline",
                "Content-Type": "application/json",
            },
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
        """
        Encode the image to base64, send it to OpenRouter, and return the
        comma-separated class list.
        """
        image_path = Path(image_path)
        b64_image = self._encode_image(image_path)
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
                            "url": f"data:{media_type};base64,{b64_image}"
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

        log.debug("Sending image to OpenRouter (%s) …", self._model)
        response = self._client.post("chat/completions", json=payload)
        if response.is_error:
            detail = response.text.strip()
            raise httpx.HTTPStatusError(
                f"{response.status_code} from OpenRouter: {detail}",
                request=response.request,
                response=response,
            )

        data = response.json()
        raw = data["choices"][0]["message"]["content"].strip()
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
    ext = path.suffix.lower()
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp"}.get(ext, "image/jpeg")
