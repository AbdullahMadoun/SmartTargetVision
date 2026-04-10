from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


class PromptGenerator:
    def __init__(self, config: dict) -> None:
        load_dotenv()
        self._enabled = bool(config.get("enabled", True))
        self._base_url = config.get("base_url", "https://openrouter.ai/api/v1").rstrip("/")
        self._model = config.get("model", "openai/gpt-4.1-mini")
        self._timeout = config.get("timeout", 45)
        self._max_tokens = config.get("max_tokens", 512)
        self._prompt = config["prompt_template"]
        self._api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OpenRouter_Key")
            or os.environ.get("OPENROUTER_KEY")
        )

    def is_ready(self) -> bool:
        return self._enabled and bool(self._api_key)

    def generate(self, image_path: str | Path, instruction: str | None = None) -> str:
        if not self.is_ready():
            raise RuntimeError("Prompt generator is not configured with an OpenRouter key.")

        image_path = Path(image_path)
        content_text = (instruction or "").strip() or "Generate detector prompts for this target."
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": self._prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{_media_type(image_path)};base64,{_b64(image_path)}"
                            },
                        },
                    ],
                },
            ],
        }

        with httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        ) as client:
            response = client.post("chat/completions", json=payload)
            if response.is_error:
                raise httpx.HTTPStatusError(
                    f"{response.status_code} from OpenRouter: {response.text.strip()}",
                    request=response.request,
                    response=response,
                )
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    @staticmethod
    def parse_classes(raw: str) -> list[str]:
        seen: set[str] = set()
        classes: list[str] = []
        for item in raw.split(","):
            label = item.strip().lower()
            if label and label not in seen:
                seen.add(label)
                classes.append(label)
        return classes


def _media_type(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/jpeg")


def _b64(path: Path) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("utf-8")
