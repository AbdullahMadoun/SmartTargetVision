from __future__ import annotations

import base64
import struct
import sys
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from drone_mcp.camera_capture import CameraFrameParseError, PNG_SIGNATURE, parse_gz_topic_camera_frame
from drone_mcp.sim_runtime import CommandResult, DockerSimulatorRuntime


class StubRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def run(self, args: list[str], *, timeout: int = 600, check: bool = True) -> CommandResult:
        self.calls.append(args)
        if not self.responses:
            raise AssertionError(f"No stubbed response left for command: {args}")
        return self.responses.pop(0)


def _protobuf_bytes_literal(payload: bytes) -> str:
    escaped = "".join(f"\\{byte:03o}" for byte in payload)
    return f'"{escaped}"'


def _decode_png_rgba(image_bytes: bytes) -> tuple[int, int, bytes]:
    assert image_bytes.startswith(PNG_SIGNATURE)
    offset = len(PNG_SIGNATURE)
    width = height = None
    idat = bytearray()

    while offset < len(image_bytes):
        length = struct.unpack(">I", image_bytes[offset : offset + 4])[0]
        chunk_type = image_bytes[offset + 4 : offset + 8]
        chunk_data = image_bytes[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height = struct.unpack(">II", chunk_data[:8])
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None:
        raise AssertionError("PNG payload did not contain IHDR.")

    raw = zlib.decompress(bytes(idat))
    return width, height, raw


class CameraCaptureTest(unittest.TestCase):
    def test_parse_rgb_frame_encodes_png_metadata(self) -> None:
        topic = "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image"
        payload = bytes([255, 0, 0, 0, 255, 0])
        message = "\n".join(
            [
                "width: 2",
                "height: 1",
                "pixel_format_type: RGB_INT8",
                f"data: {_protobuf_bytes_literal(payload)}",
            ]
        )

        frame = parse_gz_topic_camera_frame(
            message,
            topic=topic,
            container_name="drone-mcp-test",
            command=("docker", "exec", "drone-mcp-test"),
        )

        width, height, raw = _decode_png_rgba(frame.image_bytes)
        self.assertEqual((width, height), (2, 1))
        self.assertEqual(frame.mime_type, "image/png")
        self.assertEqual(frame.encoding, "png")
        self.assertEqual(frame.width, 2)
        self.assertEqual(frame.height, 1)
        self.assertEqual(frame.pixel_format_type, "RGB_INT8")
        self.assertEqual(raw[0], 0)
        self.assertEqual(raw[1:5], bytes([255, 0, 0, 255]))
        self.assertEqual(raw[5:9], bytes([0, 255, 0, 255]))
        self.assertEqual(base64.b64decode(frame.image_base64), frame.image_bytes)

    def test_parse_l_int16_frame_normalizes_to_png(self) -> None:
        topic = "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image"
        payload = bytes([0x00, 0x00, 0xFF, 0xFF])
        message = "\n".join(
            [
                "width: 2",
                "height: 1",
                "pixel_format_type: L_INT16",
                f"data: {_protobuf_bytes_literal(payload)}",
            ]
        )

        frame = parse_gz_topic_camera_frame(
            message,
            topic=topic,
            container_name="drone-mcp-test",
            command=("docker", "exec", "drone-mcp-test"),
        )

        _, _, raw = _decode_png_rgba(frame.image_bytes)
        self.assertEqual(raw[0], 0)
        self.assertEqual(raw[1:5], bytes([0, 0, 0, 255]))
        self.assertEqual(raw[5:9], bytes([255, 255, 255, 255]))

    def test_capture_camera_frame_runs_gz_topic_inside_container(self) -> None:
        topic = "/world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image"
        payload = bytes([0, 0, 0, 255, 255, 255])
        message = "\n".join(
            [
                "width: 2",
                "height: 1",
                "pixel_format_type: RGB_INT8",
                f"data: {_protobuf_bytes_literal(payload)}",
            ]
        )
        runner = StubRunner([CommandResult(0, message, "")])
        runtime = DockerSimulatorRuntime(
            ROOT,
            image="drone-mcp/sim-monocam:test",
            container_name="drone-mcp-test",
            runner=runner,
        )

        frame = runtime.capture_camera_frame(topic=topic, timeout_s=7)

        self.assertEqual(runner.calls[0][0:4], ["docker", "exec", "drone-mcp-test", "sh"])
        self.assertEqual(runner.calls[0][4], "-lc")
        self.assertIn("timeout 7s gz topic -e -n 1 -t /world/default/model/x500_mono_cam_0/link/camera_link/sensor/camera/image", runner.calls[0][5])
        self.assertEqual(frame.topic, topic)
        self.assertEqual(frame.container_name, "drone-mcp-test")
        self.assertEqual(frame.to_dict()["image_byte_length"], len(frame.image_bytes))
        self.assertEqual(base64.b64decode(frame.image_base64), frame.image_bytes)

    def test_parse_frame_rejects_missing_image_data(self) -> None:
        message = "\n".join(
            [
                "width: 2",
                "height: 1",
                "pixel_format_type: RGB_INT8",
            ]
        )

        with self.assertRaises(CameraFrameParseError):
            parse_gz_topic_camera_frame(
                message,
                topic="/camera",
                container_name="drone-mcp-test",
                command=("docker", "exec", "drone-mcp-test"),
            )


if __name__ == "__main__":
    unittest.main()
