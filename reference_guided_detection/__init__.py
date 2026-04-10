"""
vlm/__init__.py
Factory — returns the correct VLM backend based on config.yaml.

Usage:
    from vlm import build_vlm
    vlm = build_vlm(config["vlm"])
    classes = vlm.describe("photo.jpg")
"""

from vlm.base import VLMBase


def build_vlm(vlm_config: dict) -> VLMBase:
    """
    Instantiate and return the VLM backend specified in config.

    Args:
        vlm_config: The `vlm` section of the parsed config.yaml.

    Returns:
        A VLMBase subclass ready to call .describe().

    Raises:
        ValueError: Unknown mode.
    """
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
