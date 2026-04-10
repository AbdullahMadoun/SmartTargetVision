"""
vlm package facade for the flattened source layout.
"""

from vlm.base import VLMBase


def build_vlm(vlm_config: dict) -> VLMBase:
    """Instantiate the configured VLM backend."""
    mode = vlm_config.get("mode", "api").lower()

    if mode == "api":
        from vlm.openrouter import OpenRouterVLM

        return OpenRouterVLM(vlm_config)

    if mode == "local":
        from vlm.local import LocalVLM

        return LocalVLM(vlm_config)

    raise ValueError(
        f"Unknown VLM mode: '{mode}'. "
        "Set vlm.mode to 'api' or 'local' in config.yaml."
    )


__all__ = ["VLMBase", "build_vlm"]
