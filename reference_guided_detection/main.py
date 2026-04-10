"""
main.py
CLI entry point for the VLM → YOLO detector pipeline.

Usage:
    # Use a reference image
    python main.py --image path/to/photo.jpg

    # Snapshot mode: press SPACE to capture the reference from webcam
    python main.py --snapshot

    # Override config file
    python main.py --image photo.jpg --config my_config.yaml

    # Override VLM mode without editing config
    python main.py --image photo.jpg --vlm-mode local

    # Override detector model
    python main.py --image photo.jpg --weights yolov8s-world.pt
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from pipeline import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def apply_overrides(config: dict, args: argparse.Namespace) -> dict:
    """Apply CLI overrides on top of the loaded config."""
    if args.vlm_mode:
        config["vlm"]["mode"] = args.vlm_mode
    if args.vlm_model:
        mode = config["vlm"]["mode"]
        config["vlm"][mode]["model"] = args.vlm_model
    if args.weights:
        config["detector"]["weights"] = args.weights
    if args.device:
        config["detector"]["device"] = args.device
    if args.confidence is not None:
        config["detector"]["confidence"] = args.confidence
    if args.source is not None:
        config["camera"]["source"] = args.source
    return config


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vlm-yolo",
        description="VLM-prompted live detection pipeline",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--image", "-i", metavar="PATH",
                      help="Path to reference image sent to the VLM")
    mode.add_argument("--snapshot", "-s", action="store_true",
                      help="Capture reference image from webcam at runtime")

    p.add_argument("--config", "-c", default=str(ROOT / "config.yaml"),
                   help="Config file path (default: reference_guided_detection/config.yaml)")
    p.add_argument("--vlm-mode", choices=["api", "local"],
                   help="Override vlm.mode in config")
    p.add_argument("--vlm-model", metavar="MODEL_ID",
                   help="Override the VLM model string (OpenRouter or local)")
    p.add_argument("--weights", metavar="FILE",
                   help="Override detector weights file")
    p.add_argument("--device", choices=["cpu", "cuda", "mps"],
                   help="Override inference device")
    p.add_argument("--confidence", type=float, metavar="0-1",
                   help="Override detection confidence threshold")
    p.add_argument("--source", metavar="CAM",
                   help="Override camera source (int index or RTSP URL)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable DEBUG logging")
    return p


def main() -> int:
    if load_dotenv:
        load_dotenv(ROOT.parent / ".env")

    parser = build_arg_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config_path = Path(args.config)
    if not config_path.exists():
        fallback = ROOT / args.config
        if fallback.exists():
            config_path = fallback
    if not Path(config_path).exists():
        log.error("Config file not found: %s", config_path)
        return 1

    config = load_config(config_path)
    config = apply_overrides(config, args)

    try:
        pipeline = Pipeline(config)
        if args.snapshot:
            pipeline.run_with_snapshot()
        else:
            pipeline.run(args.image)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    except Exception as exc:
        log.exception("Unhandled error: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
