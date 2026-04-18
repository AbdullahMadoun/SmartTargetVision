from __future__ import annotations

import tarfile
import tempfile
import unittest
from pathlib import Path

from drone_mcp.vast_vm import SshTarget, build_tunnel_command, create_repo_bundle, read_env_file_value


class VastVmHelpersTest(unittest.TestCase):
    def test_read_env_file_value_supports_spaces_and_multiple_key_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "# comment\n"
                "OTHER_KEY = nope\n"
                "OpenRouter_Key = sk-test-value\n",
                encoding="utf-8",
            )
            value = read_env_file_value(env_path, "OPENROUTER_KEY", "OpenRouter_Key")
            self.assertEqual(value, "sk-test-value")

    def test_create_repo_bundle_excludes_pycache_and_pyc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            (root / "README.md").write_text("hello", encoding="utf-8")
            pycache_dir = root / "__pycache__"
            pycache_dir.mkdir()
            (pycache_dir / "x.pyc").write_bytes(b"junk")

            bundle_path = Path(temp_dir) / "bundle.tgz"
            create_repo_bundle(root, bundle_path)

            with tarfile.open(bundle_path, "r:gz") as archive:
                names = archive.getnames()

            self.assertIn("README.md", names)
            self.assertNotIn("__pycache__/x.pyc", names)

    def test_build_tunnel_command_forwards_operator_and_vnc_ports(self) -> None:
        target = SshTarget(host="1.2.3.4", port=39506, key_path=Path("/tmp/key"))
        command = build_tunnel_command(target)
        self.assertIn("8080:127.0.0.1:8080", command)
        self.assertIn("6080:127.0.0.1:6080", command)
        self.assertIn("5900:127.0.0.1:5900", command)
        self.assertEqual(command[-1], "root@1.2.3.4")
