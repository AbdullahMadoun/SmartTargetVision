from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.sim_runtime import DockerSimulatorRuntime, SimulatorNotReadyError

RUNTIME = DockerSimulatorRuntime(
    ROOT,
    image="drone-mcp/sim-monocam:smoke",
    container_name="drone-mcp-monocam-smoke",
)


def main() -> int:
    try:
        print("[1/3] Building derived monocam simulator image...")
        RUNTIME.build_image()
        print("[2/3] Starting simulator container...")
        RUNTIME.start()
        print("[3/3] Verifying camera topics and plugin health...")
        status = RUNTIME.wait_until_ready()
        print("Smoke test passed.")
        print("Camera topics:")
        for line in status.camera_topics:
            print(f"  {line}")
        return 0
    except SimulatorNotReadyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        RUNTIME.stop()


if __name__ == "__main__":
    raise SystemExit(main())
