from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.vast_vm import SshTarget, build_tunnel_command, create_repo_bundle, read_env_file_value


class DeployError(RuntimeError):
    """Raised when remote deployment fails."""


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise DeployError(
            f"Command failed: {' '.join(command)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def ssh(target: SshTarget, remote_command: str, *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return run(target.ssh_args() + [remote_command], timeout=timeout)


def scp_to(target: SshTarget, local_path: Path, remote_path: str, *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return run(target.scp_args() + [str(local_path), f"{target.destination()}:{remote_path}"], timeout=timeout)


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy the Drone-MCP visual operator stack to a Vast VM.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", default="root")
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--remote-root", default="/opt/drone-mcp")
    parser.add_argument("--openrouter-env-file", default="")
    parser.add_argument("--openrouter-model", default="openai/gpt-4o-mini")
    parser.add_argument("--skip-smoke-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = SshTarget(
        host=args.host,
        port=args.port,
        key_path=Path(args.ssh_key).expanduser(),
        user=args.user,
    )
    env_file_path = Path(args.openrouter_env_file).expanduser() if args.openrouter_env_file else None
    openrouter_key = ""
    if env_file_path:
        openrouter_key = read_env_file_value(
            env_file_path,
            "OPENROUTER_KEY",
            "OPENROUTER_API_KEY",
            "OpenRouter_Key",
        )

    temp_parent = ROOT / ".tmp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="drone-mcp-vm-", dir=temp_parent) as temp_dir:
        temp_root = Path(temp_dir)
        bundle_path = create_repo_bundle(ROOT, temp_root / "drone-mcp-bundle.tgz")
        env_upload_path = temp_root / "operator.env"
        env_lines = [f"OPENROUTER_MODEL={args.openrouter_model}"]
        if openrouter_key:
            env_lines.insert(0, f"OPENROUTER_KEY={openrouter_key}")
        with env_upload_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(env_lines) + "\n")

        print("[1/7] Uploading repo bundle to the Vast VM...")
        ssh(target, f"mkdir -p {shlex.quote(args.remote_root)} /tmp/drone-mcp")
        scp_to(target, bundle_path, "/tmp/drone-mcp/drone-mcp-bundle.tgz", timeout=1800)
        scp_to(target, env_upload_path, "/tmp/drone-mcp/operator.env", timeout=60)

        print("[2/7] Extracting the repo on the Vast VM...")
        ssh(
            target,
            shell_join(
                [
                    "sh",
                    "-lc",
                    (
                        f"rm -rf {shlex.quote(args.remote_root)} && "
                        f"mkdir -p {shlex.quote(args.remote_root)} && "
                        f"tar -xzf /tmp/drone-mcp/drone-mcp-bundle.tgz -C {shlex.quote(args.remote_root)}"
                    ),
                ]
            ),
            timeout=1800,
        )

        print("[3/7] Ensuring Docker is ready on the Vast VM...")
        ssh(
            target,
            shell_join(
                [
                    "sh",
                    "-lc",
                    (
                        f"chmod +x {args.remote_root}/scripts/bootstrap_vast_vm.sh {args.remote_root}/scripts/run_remote_operator_stack.sh && "
                        f"DOCKER_API_VERSION=1.43 {args.remote_root}/scripts/bootstrap_vast_vm.sh"
                    ),
                ]
            ),
            timeout=1800,
        )

        if not args.skip_smoke_test:
            print("[4/7] Clearing old containers before smoke test...")
            ssh(
                target,
                shell_join(
                    [
                        "sh",
                        "-lc",
                        "DOCKER_API_VERSION=1.43 docker rm -f drone-mcp-operator-web drone-mcp-sim-visual >/dev/null 2>&1 || true",
                    ]
                ),
                timeout=120,
            )

            print("[5/7] Running the remote operator smoke test...")
            ssh(
                target,
                shell_join(
                    [
                        "sh",
                        "-lc",
                        f"cd {args.remote_root} && DOCKER_API_VERSION=1.43 python3 scripts/smoke_test_operator_web.py",
                    ]
                ),
                timeout=7200,
            )

        print("[6/8] Building images and starting the operator stack...")
        ssh(
            target,
            shell_join(
                [
                    "sh",
                    "-lc",
                    (
                        f"set -a && . /tmp/drone-mcp/operator.env && set +a && "
                        f"DOCKER_API_VERSION=1.43 REPO_ROOT={shlex.quote(args.remote_root)} {args.remote_root}/scripts/run_remote_operator_stack.sh"
                    ),
                ]
            ),
            timeout=7200,
        )

        print("[7/8] Verifying remote operator health...")
        health = ssh(
            target,
            shell_join(
                [
                    "python3",
                    "-c",
                    (
                        "import json, urllib.request; "
                        "print(json.loads(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=15).read().decode('utf-8')))"
                    ),
                ]
            ),
            timeout=60,
        )
        print(health.stdout.strip())

        print("[8/8] Auto-starting the simulation...")
        try:
            ssh(
                target,
                shell_join(
                    [
                        "python3",
                        "-c",
                        (
                            "import json, urllib.request; "
                            "req = urllib.request.Request('http://127.0.0.1:8080/api/tool', "
                            "data=json.dumps({'name':'start_simulation','arguments':{'timeout':'180'}}).encode(), "
                            "headers={'Content-Type':'application/json'}, method='POST'); "
                            "resp = urllib.request.urlopen(req, timeout=300); "
                            "print(json.loads(resp.read().decode('utf-8')).get('text',''))"
                        ),
                    ]
                ),
                timeout=600,
            )
        except Exception as exc:
            print(f"  Warning: auto-start failed ({exc}). You can start manually from the UI.")

    # Save connection info for the connect script.
    connection_file = ROOT / ".vast-connection.json"
    connection_info = {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "ssh_key": str(Path(args.ssh_key).expanduser()),
    }
    with connection_file.open("w", encoding="utf-8") as f:
        json.dump(connection_info, f, indent=2)
    print(f"\n  Connection info saved to {connection_file.name}")

    tunnel_command = build_tunnel_command(target)
    print("")
    print("=" * 60)
    print("  DEPLOYMENT COMPLETE — SIMULATION RUNNING")
    print("=" * 60)
    print("")
    print("  To connect now, just run:")
    print("")
    print("    .\\scripts\\vast_connect.ps1")
    print("")
    print("  Or manually:")
    print("    1. " + " ".join(shlex.quote(part) for part in tunnel_command))
    print("    2. Open http://127.0.0.1:8080")
    print("")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
