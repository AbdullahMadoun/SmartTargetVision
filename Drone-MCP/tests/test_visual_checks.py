from __future__ import annotations

import base64
import hashlib
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.visual_checks import (
    WEBSOCKET_GUID,
    WindowGeometry,
    analyze_xwd_visual_signal,
    build_viewport_probe_regions,
    extract_window_geometries,
    probe_rfb_banner,
    probe_websocket_upgrade,
)


def _make_xwd(width: int, height: int, pixels: list[tuple[int, int, int]]) -> bytes:
    window_name = b"root\0"
    header_size = struct.calcsize("25I") + len(window_name)
    header = struct.pack(
        "<25I",
        header_size,
        7,
        2,
        24,
        width,
        height,
        0,
        0,
        32,
        0,
        32,
        32,
        width * 4,
        4,
        0x00FF0000,
        0x0000FF00,
        0x000000FF,
        8,
        256,
        0,
        width,
        height,
        0,
        0,
        0,
    )
    pixel_bytes = bytearray()
    for red, green, blue in pixels:
        pixel_value = (red << 16) | (green << 8) | blue
        pixel_bytes.extend(pixel_value.to_bytes(4, byteorder="little", signed=False))
    return header + window_name + pixel_bytes


def _start_test_server(handler) -> tuple[threading.Thread, int]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def runner() -> None:
        try:
            connection, _ = server.accept()
            with connection:
                handler(connection)
        finally:
            server.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return thread, port


class VisualChecksTest(unittest.TestCase):
    def test_probe_rfb_banner_reads_vnc_handshake(self) -> None:
        def handler(connection: socket.socket) -> None:
            connection.sendall(b"RFB 003.008\n")

        thread, port = _start_test_server(handler)
        try:
            banner = probe_rfb_banner("127.0.0.1", port)
        finally:
            thread.join(timeout=2)

        self.assertEqual(banner, "RFB 003.008")

    def test_probe_websocket_upgrade_accepts_valid_switching_protocols_response(self) -> None:
        def handler(connection: socket.socket) -> None:
            request = bytearray()
            while b"\r\n\r\n" not in request:
                request.extend(connection.recv(4096))
            headers = request.decode("ascii", errors="replace").split("\r\n")
            key_line = next(
                line for line in headers if line.lower().startswith("sec-websocket-key:")
            )
            key = key_line.split(":", 1)[1].strip()
            accept = base64.b64encode(hashlib.sha1(f"{key}{WEBSOCKET_GUID}".encode("ascii")).digest()).decode(
                "ascii"
            )
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            ).encode("ascii")
            connection.sendall(response)

        thread, port = _start_test_server(handler)
        try:
            status_line = probe_websocket_upgrade("127.0.0.1", port)
        finally:
            thread.join(timeout=2)

        self.assertIn("101", status_line)

    def test_extract_window_geometries_finds_matching_gazebo_windows(self) -> None:
        tree_text = "\n".join(
            [
                '0x1000012 "Gazebo Sim": ("gz-sim-gui" "Gazebo GUI")  1280x720+10+10  +10+10',
                '0x2000012 "Other Window": ("other" "Other")  200x100+5+5  +5+5',
            ]
        )

        windows = extract_window_geometries(tree_text, ("Gazebo Sim", "Gazebo GUI"))

        self.assertEqual(
            windows,
            (
                WindowGeometry(
                    title="Gazebo Sim",
                    window_id="0x1000012",
                    x=10,
                    y=10,
                    width=1280,
                    height=720,
                ),
            ),
        )

    def test_build_viewport_probe_regions_targets_center_and_lower_center(self) -> None:
        window = WindowGeometry(
            title="Gazebo Sim",
            window_id="0x1000012",
            x=10,
            y=20,
            width=1000,
            height=800,
        )

        center_region, lower_region = build_viewport_probe_regions(window)

        self.assertLess(center_region[0], lower_region[0] + 1)
        self.assertGreater(center_region[2], 0)
        self.assertGreater(center_region[3], 0)
        self.assertGreater(lower_region[2], 0)
        self.assertGreater(lower_region[3], 0)
        self.assertGreater(lower_region[1], center_region[1])

    def test_analyze_xwd_visual_signal_rejects_flat_dark_frame(self) -> None:
        pixels = [(0, 0, 0)] * (32 * 32)
        report = analyze_xwd_visual_signal(_make_xwd(32, 32, pixels))

        self.assertFalse(report.looks_rendered)
        self.assertEqual(report.unique_color_buckets, 1)
        self.assertEqual(report.max_luma, 0)

    def test_analyze_xwd_visual_signal_accepts_varied_frame_region(self) -> None:
        pixels: list[tuple[int, int, int]] = []
        for y in range(64):
            for x in range(64):
                if 8 <= x < 56 and 8 <= y < 56:
                    pixels.append(((x * 5) % 256, (y * 3) % 256, ((x + y) * 7) % 256))
                else:
                    pixels.append((0, 0, 0))

        report = analyze_xwd_visual_signal(_make_xwd(64, 64, pixels), region=(8, 8, 48, 48))

        self.assertTrue(report.looks_rendered)
        self.assertGreaterEqual(report.unique_color_buckets, 8)
        self.assertGreater(report.max_luma - report.min_luma, 16)

    def test_analyze_xwd_visual_signal_rejects_colored_border_with_blank_center(self) -> None:
        pixels: list[tuple[int, int, int]] = []
        width = 400
        height = 300
        blank_left = 100
        blank_top = 75
        blank_right = 300
        blank_bottom = 225
        for y in range(height):
            for x in range(width):
                if blank_left <= x < blank_right and blank_top <= y < blank_bottom:
                    pixels.append((0, 0, 0))
                else:
                    pixels.append(((x * 13) % 256, (y * 7) % 256, ((x + y) * 5) % 256))

        region = build_viewport_probe_regions(
            WindowGeometry(
                title="Gazebo Sim",
                window_id="0x1000012",
                x=0,
                y=0,
                width=width,
                height=height,
            )
        )[0]
        report = analyze_xwd_visual_signal(_make_xwd(width, height, pixels), region=region)

        self.assertFalse(report.looks_rendered)
        self.assertEqual(report.unique_color_buckets, 1)
        self.assertEqual(report.min_luma, 0)
        self.assertEqual(report.max_luma, 0)


if __name__ == "__main__":
    unittest.main()
