from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.sim_runtime import DockerSimulatorRuntime, SimulatorNotReadyError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the verified monocam simulator runtime.")
    parser.add_argument(
        "action",
        choices=("build", "start", "stop", "reset", "status", "wait-ready", "logs"),
    )
    parser.add_argument("--image", default="drone-mcp/sim-monocam:local")
    parser.add_argument("--container-name", default="drone-mcp-sim-monocam")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--lines", type=int, default=200)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runtime = DockerSimulatorRuntime(
        ROOT,
        image=args.image,
        container_name=args.container_name,
    )

    try:
        if args.action == "build":
            runtime.build_image()
            print("Built simulator image.")
            return 0
        if args.action == "start":
            runtime.start()
            print("Started simulator container.")
            return 0
        if args.action == "stop":
            runtime.stop()
            print("Stopped simulator container.")
            return 0
        if args.action == "reset":
            runtime.reset()
            print("Reset simulator container.")
            return 0
        if args.action == "status":
            print(json.dumps(runtime.status().to_dict(), indent=2))
            return 0
        if args.action == "wait-ready":
            status = runtime.wait_until_ready(timeout_s=args.timeout)
            print(json.dumps(status.to_dict(), indent=2))
            return 0
        if args.action == "logs":
            print(runtime.logs_tail(lines=args.lines))
            return 0
    except SimulatorNotReadyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
