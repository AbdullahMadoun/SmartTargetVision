from __future__ import annotations

import base64
import hashlib
import os
import re
import socket
import struct
from dataclasses import dataclass
from typing import Iterable


WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WINDOW_GEOMETRY_RE = re.compile(r"(?P<width>\d+)x(?P<height>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)")
WINDOW_ID_RE = re.compile(r"^(?P<window_id>0x[0-9a-fA-F]+)")
XWD_FILE_VERSION = 7
XWD_HEADER_FORMAT = "25I"
XWD_HEADER_SIZE = struct.calcsize(XWD_HEADER_FORMAT)
XWD_COLOR_SIZE = 12
LSB_FIRST = 0
MSB_FIRST = 1


@dataclass(frozen=True, slots=True)
class WindowGeometry:
    title: str
    window_id: str | None
    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class VisualSignalReport:
    region_width: int
    region_height: int
    sampled_pixels: int
    unique_color_buckets: int
    min_luma: int
    max_luma: int
    non_dark_fraction: float
    looks_rendered: bool

    def describe(self) -> str:
        return (
            f"region={self.region_width}x{self.region_height}, "
            f"samples={self.sampled_pixels}, "
            f"unique_buckets={self.unique_color_buckets}, "
            f"luma_range={self.min_luma}-{self.max_luma}, "
            f"non_dark_fraction={self.non_dark_fraction:.3f}, "
            f"looks_rendered={'yes' if self.looks_rendered else 'no'}"
        )


@dataclass(frozen=True, slots=True)
class _XwdHeader:
    endianness: str
    byte_order: int
    width: int
    height: int
    bits_per_pixel: int
    bytes_per_line: int
    red_mask: int
    green_mask: int
    blue_mask: int
    data_offset: int


def extract_window_geometries(window_tree_text: str, title_markers: Iterable[str]) -> tuple[WindowGeometry, ...]:
    markers = tuple(marker for marker in title_markers if marker)
    windows: list[WindowGeometry] = []
    for raw_line in window_tree_text.splitlines():
        line = raw_line.strip()
        if not line or not any(marker in line for marker in markers):
            continue
        geometry_match = WINDOW_GEOMETRY_RE.search(line)
        if geometry_match is None:
            continue
        window_id_match = WINDOW_ID_RE.search(line)
        title_match = re.search(r'"([^"]+)"', line)
        title = title_match.group(1) if title_match else line
        windows.append(
            WindowGeometry(
                title=title,
                window_id=window_id_match.group("window_id") if window_id_match else None,
                x=int(geometry_match.group("x")),
                y=int(geometry_match.group("y")),
                width=int(geometry_match.group("width")),
                height=int(geometry_match.group("height")),
            )
        )
    return tuple(windows)


def build_viewport_probe_regions(window: WindowGeometry) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Return viewport-focused regions that avoid title bars and side chrome.

    The first region targets the center of the 3D canvas. The second shifts
    lower to catch layouts where the main render area sits beneath a toolbar.
    """

    width = max(1, window.width)
    height = max(1, window.height)

    center_width = max(160, min(width, int(round(width * 0.42))))
    center_height = max(120, min(height, int(round(height * 0.34))))
    lower_height = max(120, min(height, int(round(height * 0.30))))
    region_width = min(center_width, width)

    center_x = window.x + max(0, (width - region_width) // 2)
    center_y = window.y + max(0, int(round(height * 0.26)))
    lower_x = center_x
    lower_y = window.y + max(0, int(round(height * 0.42)))

    center_region = _resolve_region(
        (center_x, center_y, region_width, center_height),
        width=window.width,
        height=window.height,
    )
    lower_region = _resolve_region(
        (lower_x, lower_y, region_width, lower_height),
        width=window.width,
        height=window.height,
    )
    return (
        center_region[0],
        center_region[1],
        center_region[2] - center_region[0],
        center_region[3] - center_region[1],
    ), (
        lower_region[0],
        lower_region[1],
        lower_region[2] - lower_region[0],
        lower_region[3] - lower_region[1],
    )


def probe_rfb_banner(host: str, port: int, *, timeout_s: float = 5.0) -> str:
    with socket.create_connection((host, port), timeout=timeout_s) as connection:
        banner = connection.recv(12).decode("ascii", errors="replace").strip()
    if not banner.startswith("RFB "):
        raise RuntimeError(f"Unexpected VNC banner from {host}:{port}: {banner!r}")
    return banner


def probe_websocket_upgrade(host: str, port: int, path: str = "/websockify", *, timeout_s: float = 5.0) -> str:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    expected_accept = _expected_websocket_accept(key)
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")

    with socket.create_connection((host, port), timeout=timeout_s) as connection:
        connection.sendall(request)
        response = _recv_http_headers(connection)

    header_text = response.decode("ascii", errors="replace")
    lines = [line for line in header_text.split("\r\n") if line]
    if not lines:
        raise RuntimeError(f"Empty websocket upgrade response from {host}:{port}{path}")
    status_line = lines[0]
    if " 101 " not in f" {status_line} ":
        raise RuntimeError(f"Websocket upgrade failed for {host}:{port}{path}: {status_line}")

    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, separator, value = line.partition(":")
        if not separator:
            continue
        headers[name.strip().lower()] = value.strip()

    if headers.get("sec-websocket-accept", "") != expected_accept:
        raise RuntimeError(
            "Websocket upgrade returned an unexpected Sec-WebSocket-Accept header: "
            f"{headers.get('sec-websocket-accept', '')!r}"
        )
    return status_line


def analyze_xwd_visual_signal(
    xwd_bytes: bytes,
    *,
    region: tuple[int, int, int, int] | None = None,
) -> VisualSignalReport:
    header = _parse_xwd_header(xwd_bytes)
    x0, y0, x1, y1 = _resolve_region(region, width=header.width, height=header.height)

    sample_columns = min(96, max(8, x1 - x0))
    sample_rows = min(54, max(8, y1 - y0))
    x_step = max(1, (x1 - x0) // sample_columns)
    y_step = max(1, (y1 - y0) // sample_rows)
    bytes_per_pixel = header.bits_per_pixel // 8
    pixel_byteorder = "little" if header.byte_order == LSB_FIRST else "big"

    sample_count = 0
    unique_color_buckets: set[tuple[int, int, int]] = set()
    min_luma = 255
    max_luma = 0
    non_dark_count = 0

    for y in range(y0, y1, y_step):
        row_offset = header.data_offset + y * header.bytes_per_line
        for x in range(x0, x1, x_step):
            pixel_offset = row_offset + x * bytes_per_pixel
            pixel_bytes = xwd_bytes[pixel_offset : pixel_offset + bytes_per_pixel]
            if len(pixel_bytes) < bytes_per_pixel:
                raise ValueError("XWD pixel data ended unexpectedly.")
            pixel_value = int.from_bytes(pixel_bytes, byteorder=pixel_byteorder, signed=False)
            red = _extract_channel(pixel_value, header.red_mask)
            green = _extract_channel(pixel_value, header.green_mask)
            blue = _extract_channel(pixel_value, header.blue_mask)
            luma = int(round((0.2126 * red) + (0.7152 * green) + (0.0722 * blue)))

            sample_count += 1
            unique_color_buckets.add((red >> 4, green >> 4, blue >> 4))
            min_luma = min(min_luma, luma)
            max_luma = max(max_luma, luma)
            if luma >= 12:
                non_dark_count += 1

    if sample_count == 0:
        raise ValueError("No pixels were sampled from the requested XWD region.")

    non_dark_fraction = non_dark_count / sample_count
    unique_bucket_count = len(unique_color_buckets)
    looks_rendered = (
        sample_count >= 64
        and unique_bucket_count >= 8
        and (max_luma - min_luma) >= 16
        and non_dark_fraction >= 0.01
    )
    return VisualSignalReport(
        region_width=x1 - x0,
        region_height=y1 - y0,
        sampled_pixels=sample_count,
        unique_color_buckets=unique_bucket_count,
        min_luma=min_luma,
        max_luma=max_luma,
        non_dark_fraction=non_dark_fraction,
        looks_rendered=looks_rendered,
    )


def _expected_websocket_accept(key: str) -> str:
    digest = hashlib.sha1(f"{key}{WEBSOCKET_GUID}".encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _recv_http_headers(connection: socket.socket) -> bytes:
    chunks = bytearray()
    while b"\r\n\r\n" not in chunks:
        chunk = connection.recv(4096)
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


def _parse_xwd_header(xwd_bytes: bytes) -> _XwdHeader:
    if len(xwd_bytes) < XWD_HEADER_SIZE:
        raise ValueError("XWD payload is too small to contain a header.")

    for endianness in ("<", ">"):
        values = struct.unpack(f"{endianness}{XWD_HEADER_FORMAT}", xwd_bytes[:XWD_HEADER_SIZE])
        header_size = values[0]
        file_version = values[1]
        byte_order = values[7]
        bits_per_pixel = values[11]
        bytes_per_line = values[12]
        red_mask = values[15]
        green_mask = values[16]
        blue_mask = values[17]
        ncolors = values[19]
        width = values[4]
        height = values[5]
        data_offset = header_size + (ncolors * XWD_COLOR_SIZE)

        if file_version != XWD_FILE_VERSION:
            continue
        if header_size < XWD_HEADER_SIZE or data_offset > len(xwd_bytes):
            continue
        if byte_order not in {LSB_FIRST, MSB_FIRST}:
            continue
        if bits_per_pixel not in {24, 32}:
            continue
        if bytes_per_line <= 0 or width <= 0 or height <= 0:
            continue

        return _XwdHeader(
            endianness=endianness,
            byte_order=byte_order,
            width=width,
            height=height,
            bits_per_pixel=bits_per_pixel,
            bytes_per_line=bytes_per_line,
            red_mask=red_mask,
            green_mask=green_mask,
            blue_mask=blue_mask,
            data_offset=data_offset,
        )

    raise ValueError("Unsupported or invalid XWD payload.")


def _resolve_region(
    region: tuple[int, int, int, int] | None,
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    if region is None:
        return 0, 0, width, height

    x, y, region_width, region_height = region
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(width, x + max(0, region_width))
    y1 = min(height, y + max(0, region_height))
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"Requested XWD region is out of bounds: {region}")
    return x0, y0, x1, y1


def _extract_channel(pixel_value: int, mask: int) -> int:
    if mask == 0:
        return 0
    lowest_bit = mask & -mask
    shift = lowest_bit.bit_length() - 1
    raw_value = (pixel_value & mask) >> shift
    max_value = mask >> shift
    if max_value <= 0:
        return 0
    return int(round((raw_value * 255) / max_value))
