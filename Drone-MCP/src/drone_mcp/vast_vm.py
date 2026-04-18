from __future__ import annotations

import tarfile
from dataclasses import dataclass
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".tmp",
    ".venv",
    "__pycache__",
    "venv",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_NAMES = {".DS_Store"}


@dataclass(frozen=True, slots=True)
class SshTarget:
    host: str
    port: int
    key_path: Path
    user: str = "root"

    def destination(self) -> str:
        return f"{self.user}@{self.host}"

    def ssh_args(self) -> list[str]:
        return [
            "ssh",
            "-i",
            str(self.key_path),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-p",
            str(self.port),
            self.destination(),
        ]

    def scp_args(self) -> list[str]:
        return [
            "scp",
            "-i",
            str(self.key_path),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-P",
            str(self.port),
        ]


def read_env_file_value(env_path: Path, *keys: str) -> str:
    wanted = {key.strip() for key in keys if key.strip()}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        normalized_key = key.strip()
        if normalized_key.startswith("export "):
            normalized_key = normalized_key.removeprefix("export ").strip()
        if normalized_key not in wanted:
            continue
        return value.strip().strip("'\"")
    return ""


def should_exclude(relative_path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in relative_path.parts):
        return True
    if relative_path.name in EXCLUDED_NAMES:
        return True
    return relative_path.suffix in EXCLUDED_SUFFIXES


def create_repo_bundle(repo_root: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(repo_root.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(repo_root)
            if should_exclude(relative_path):
                continue
            archive.add(path, arcname=str(relative_path))
    return destination


def build_tunnel_command(
    target: SshTarget,
    *,
    operator_port: int = 8080,
    vnc_port: int = 6080,
    raw_vnc_port: int = 5900,
) -> list[str]:
    return target.ssh_args()[:1] + [
        "-i",
        str(target.key_path),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-N",
        "-L",
        f"{operator_port}:127.0.0.1:8080",
        "-L",
        f"{vnc_port}:127.0.0.1:6080",
        "-L",
        f"{raw_vnc_port}:127.0.0.1:5900",
        "-p",
        str(target.port),
        target.destination(),
    ]
