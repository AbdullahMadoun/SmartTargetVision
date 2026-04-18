from __future__ import annotations

import ast
import base64
import struct
import zlib
from dataclasses import dataclass
from typing import Sequence


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

COMPRESSED_IMAGE_MIME_TYPES = {
    "COMPRESSED_JPEG": "image/jpeg",
    "COMPRESSED_PNG": "image/png",
}

RAW_PIXEL_FORMAT_CHANNELS: dict[str, tuple[int, int]] = {
    "L_INT8": (1, 1),
    "L_INT16": (1, 2),
    "R_FLOAT16": (1, 2),
    "R_FLOAT32": (1, 4),
    "RGB_INT8": (3, 1),
    "BGR_INT8": (3, 1),
    "RGBA_INT8": (4, 1),
    "BGRA_INT8": (4, 1),
    "RGB_INT16": (3, 2),
    "BGR_INT16": (3, 2),
    "RGBA_INT16": (4, 2),
    "BGRA_INT16": (4, 2),
}

FIELD_NAMES = {
    "data",
    "height",
    "is_bigendian",
    "pixel_format_type",
    "step",
    "topic",
    "width",
}


@dataclass(frozen=True, slots=True)
class CameraFrameCapture:
    container_name: str
    topic: str
    command: tuple[str, ...]
    width: int
    height: int
    pixel_format_type: str
    mime_type: str
    encoding: str
    image_bytes: bytes
    image_base64: str
    step: int | None = None
    is_bigendian: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "container_name": self.container_name,
            "topic": self.topic,
            "command": list(self.command),
            "width": self.width,
            "height": self.height,
            "pixel_format_type": self.pixel_format_type,
            "mime_type": self.mime_type,
            "encoding": self.encoding,
            "image_base64": self.image_base64,
            "image_byte_length": len(self.image_bytes),
            "step": self.step,
            "is_bigendian": self.is_bigendian,
        }


class CameraFrameParseError(ValueError):
    """Raised when a gz topic echo cannot be converted into an image."""


def parse_gz_topic_camera_frame(
    message_text: str,
    *,
    topic: str,
    container_name: str,
    command: Sequence[str],
) -> CameraFrameCapture:
    fields = _extract_fields(message_text)

    width = _require_int(fields.get("width"), field_name="width")
    height = _require_int(fields.get("height"), field_name="height")
    pixel_format_type = str(fields.get("pixel_format_type") or "UNKNOWN_PIXEL_FORMAT").strip()
    step = _optional_int(fields.get("step"), field_name="step")
    is_bigendian = _optional_bool(fields.get("is_bigendian"))
    data = fields.get("data")
    if not isinstance(data, bytes) or not data:
        raise CameraFrameParseError("Camera frame message did not contain image bytes.")

    image_bytes, mime_type, encoding = _encode_camera_frame(
        width=width,
        height=height,
        pixel_format_type=pixel_format_type,
        data=data,
        step=step,
        is_bigendian=is_bigendian,
    )
    return CameraFrameCapture(
        container_name=container_name,
        topic=topic,
        command=tuple(command),
        width=width,
        height=height,
        pixel_format_type=pixel_format_type,
        mime_type=mime_type,
        encoding=encoding,
        image_bytes=image_bytes,
        image_base64=base64.b64encode(image_bytes).decode("ascii"),
        step=step,
        is_bigendian=is_bigendian,
    )


def _extract_fields(message_text: str) -> dict[str, object]:
    fields: dict[str, object] = {}
    for raw_line in message_text.splitlines():
        line = raw_line.strip()
        if not line or line in {"{", "}"}:
            continue
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if key not in FIELD_NAMES:
            continue
        value_text = raw_value.strip()
        if key == "data":
            fields[key] = _parse_bytes_literal(value_text)
        elif key in {"width", "height", "step"}:
            fields[key] = int(value_text)
        elif key == "is_bigendian":
            fields[key] = _parse_optional_bool_text(value_text)
        else:
            fields[key] = _strip_quotes(value_text)
    return fields


def _parse_bytes_literal(value_text: str) -> bytes:
    if not value_text:
        return b""
    if value_text.startswith("b'") or value_text.startswith('b"'):
        return ast.literal_eval(value_text)
    if value_text.startswith("'") or value_text.startswith('"'):
        return ast.literal_eval(f"b{value_text}")
    return bytes.fromhex(value_text)


def _encode_camera_frame(
    *,
    width: int,
    height: int,
    pixel_format_type: str,
    data: bytes,
    step: int | None,
    is_bigendian: bool | None,
) -> tuple[bytes, str, str]:
    if data.startswith(PNG_SIGNATURE) or pixel_format_type == "COMPRESSED_PNG":
        return data, "image/png", "png"
    if pixel_format_type == "COMPRESSED_JPEG" or data.startswith(b"\xff\xd8\xff"):
        return data, "image/jpeg", "jpeg"

    if pixel_format_type not in RAW_PIXEL_FORMAT_CHANNELS:
        raise CameraFrameParseError(f"Unsupported camera pixel format: {pixel_format_type}")

    channels, bytes_per_channel = RAW_PIXEL_FORMAT_CHANNELS[pixel_format_type]
    row_bytes = width * channels * bytes_per_channel
    row_stride = step or row_bytes
    if row_stride < row_bytes:
        raise CameraFrameParseError(
            f"Camera frame step {row_stride} is smaller than the packed row size {row_bytes}."
        )
    expected_bytes = row_stride * height
    if len(data) < expected_bytes:
        raise CameraFrameParseError(
            f"Camera frame data ended early: expected at least {expected_bytes} bytes, got {len(data)}."
        )

    rgba_bytes = bytearray()
    if channels == 1:
        rgba_bytes.extend(
            _decode_single_channel(
                data[:expected_bytes],
                width=width,
                height=height,
                bytes_per_channel=bytes_per_channel,
                row_stride=row_stride,
                is_bigendian=is_bigendian,
            )
        )
    else:
        rgba_bytes.extend(
            _decode_color_channels(
                data[:expected_bytes],
                width=width,
                height=height,
                channels=channels,
                bytes_per_channel=bytes_per_channel,
                row_stride=row_stride,
                pixel_format_type=pixel_format_type,
                is_bigendian=is_bigendian,
            )
        )
    return _encode_png(width, height, bytes(rgba_bytes)), "image/png", "png"


def _decode_single_channel(
    data: bytes,
    *,
    width: int,
    height: int,
    bytes_per_channel: int,
    row_stride: int,
    is_bigendian: bool | None,
) -> bytes:
    values: list[float] = []
    for row_index in range(height):
        row = data[row_index * row_stride : row_index * row_stride + width * bytes_per_channel]
        if len(row) < width * bytes_per_channel:
            raise CameraFrameParseError("Camera frame data ended in the middle of a row.")
        if bytes_per_channel == 1:
            values.extend(row)
        elif bytes_per_channel == 2:
            endian = "big" if is_bigendian else "little"
            values.extend(
                int.from_bytes(row[offset : offset + 2], byteorder=endian, signed=False)
                for offset in range(0, len(row), 2)
            )
        elif bytes_per_channel == 4:
            endian = "big" if is_bigendian else "little"
            values.extend(
                struct.unpack(f"{'>' if endian == 'big' else '<'}f", row[offset : offset + 4])[0]
                for offset in range(0, len(row), 4)
            )
        else:
            raise CameraFrameParseError("Unsupported single-channel byte depth.")

    normalized = _normalize_scalar_values(values, bytes_per_channel=bytes_per_channel)
    rgba = bytearray()
    for value in normalized:
        rgba.extend((value, value, value, 255))
    return bytes(rgba)


def _decode_color_channels(
    data: bytes,
    *,
    width: int,
    height: int,
    channels: int,
    bytes_per_channel: int,
    row_stride: int,
    pixel_format_type: str,
    is_bigendian: bool | None,
) -> bytes:
    rgba = bytearray()
    endian = "big" if is_bigendian else "little"
    for row_index in range(height):
        row = data[row_index * row_stride : row_index * row_stride + width * channels * bytes_per_channel]
        if len(row) < width * channels * bytes_per_channel:
            raise CameraFrameParseError("Camera frame data ended in the middle of a row.")
        for offset in range(0, len(row), channels * bytes_per_channel):
            pixel = row[offset : offset + channels * bytes_per_channel]
            if bytes_per_channel == 1:
                channel_values = list(pixel)
            elif bytes_per_channel == 2:
                channel_values = [
                    int.from_bytes(pixel[channel_offset : channel_offset + 2], byteorder=endian, signed=False) // 257
                    for channel_offset in range(0, len(pixel), 2)
                ]
            else:
                raise CameraFrameParseError(
                    f"Unsupported color channel depth for {pixel_format_type}: {bytes_per_channel} bytes."
                )

            if pixel_format_type.startswith("BGR"):
                if channels == 3:
                    red, green, blue = channel_values[2], channel_values[1], channel_values[0]
                    alpha = 255
                else:
                    blue, green, red, alpha = channel_values
            else:
                if channels == 3:
                    red, green, blue = channel_values
                    alpha = 255
                else:
                    red, green, blue, alpha = channel_values
            rgba.extend((red, green, blue, alpha))
    return bytes(rgba)


def _normalize_scalar_values(values: list[float], *, bytes_per_channel: int) -> list[int]:
    if not values:
        return []
    if bytes_per_channel == 1:
        return [int(max(0, min(255, round(value)))) for value in values]
    min_value = min(values)
    max_value = max(values)
    if max_value <= min_value:
        fill = 255 if max_value > 0 else 0
        return [fill for _ in values]
    scale = 255.0 / (max_value - min_value)
    return [int(max(0, min(255, round((value - min_value) * scale)))) for value in values]


def _encode_png(width: int, height: int, rgba_bytes: bytes) -> bytes:
    row_bytes = width * 4
    expected = row_bytes * height
    if len(rgba_bytes) != expected:
        raise CameraFrameParseError(
            f"RGBA payload length does not match image dimensions: expected {expected}, got {len(rgba_bytes)}."
        )

    scanlines = bytearray()
    for row_index in range(height):
        start = row_index * row_bytes
        scanlines.append(0)
        scanlines.extend(rgba_bytes[start : start + row_bytes])
    compressed = zlib.compress(bytes(scanlines), level=6)
    return (
        PNG_SIGNATURE
        + _png_chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0),
        )
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _require_int(value: object | None, *, field_name: str) -> int:
    if value is None:
        raise CameraFrameParseError(f"Camera frame message did not include {field_name}.")
    return int(value)


def _optional_int(value: object | None, *, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CameraFrameParseError(f"Invalid {field_name} value: {value!r}") from exc


def _optional_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        parsed = value.strip().lower()
        if parsed in {"1", "true", "yes", "on"}:
            return True
        if parsed in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    raise CameraFrameParseError(f"Invalid is_bigendian value: {value!r}")


def _parse_optional_bool_text(value_text: str) -> bool:
    parsed = value_text.strip().lower()
    if parsed in {"1", "true", "yes", "on"}:
        return True
    if parsed in {"0", "false", "no", "off"}:
        return False
    raise CameraFrameParseError(f"Invalid boolean value: {value_text!r}")


def _strip_quotes(value_text: str) -> str:
    if (value_text.startswith('"') and value_text.endswith('"')) or (
        value_text.startswith("'") and value_text.endswith("'")
    ):
        return value_text[1:-1]
    return value_text
