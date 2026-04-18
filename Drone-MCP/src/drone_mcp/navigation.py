from __future__ import annotations

import math
from dataclasses import dataclass


EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True, slots=True)
class GeoPoint:
    latitude_deg: float
    longitude_deg: float

    def to_dict(self) -> dict[str, float]:
        return {
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
        }


def haversine_distance_m(
    latitude_a_deg: float,
    longitude_a_deg: float,
    latitude_b_deg: float,
    longitude_b_deg: float,
) -> float:
    lat_a = math.radians(latitude_a_deg)
    lon_a = math.radians(longitude_a_deg)
    lat_b = math.radians(latitude_b_deg)
    lon_b = math.radians(longitude_b_deg)
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    a = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def project_local_m(
    latitude_deg: float,
    longitude_deg: float,
    reference_latitude_deg: float,
    reference_longitude_deg: float,
) -> tuple[float, float]:
    ref_lat_rad = math.radians(reference_latitude_deg)
    x_m = math.radians(longitude_deg - reference_longitude_deg) * EARTH_RADIUS_M * math.cos(ref_lat_rad)
    y_m = math.radians(latitude_deg - reference_latitude_deg) * EARTH_RADIUS_M
    return x_m, y_m


def unproject_local_m(
    x_m: float,
    y_m: float,
    reference_latitude_deg: float,
    reference_longitude_deg: float,
) -> GeoPoint:
    ref_lat_rad = math.radians(reference_latitude_deg)
    latitude_deg = reference_latitude_deg + math.degrees(y_m / EARTH_RADIUS_M)
    longitude_deg = reference_longitude_deg + math.degrees(
        x_m / (EARTH_RADIUS_M * max(math.cos(ref_lat_rad), 1e-9))
    )
    return GeoPoint(latitude_deg=latitude_deg, longitude_deg=longitude_deg)


def normalize_polygon(points: list[GeoPoint]) -> list[GeoPoint]:
    cleaned = list(points)
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
        cleaned = cleaned[:-1]
    if len(cleaned) < 3:
        raise ValueError("Polygon must contain at least 3 distinct points.")
    return cleaned


def generate_lawnmower_pattern(
    polygon: list[GeoPoint],
    *,
    strip_spacing_m: float = 25.0,
    waypoint_spacing_m: float = 25.0,
) -> list[GeoPoint]:
    if strip_spacing_m <= 0:
        raise ValueError("strip_spacing_m must be greater than 0.")
    if waypoint_spacing_m <= 0:
        raise ValueError("waypoint_spacing_m must be greater than 0.")

    normalized = normalize_polygon(polygon)
    reference = normalized[0]
    local_points = [
        project_local_m(
            point.latitude_deg,
            point.longitude_deg,
            reference.latitude_deg,
            reference.longitude_deg,
        )
        for point in normalized
    ]

    min_y = min(point[1] for point in local_points)
    max_y = max(point[1] for point in local_points)
    if math.isclose(min_y, max_y):
        raise ValueError("Polygon must cover a non-zero area.")

    rows: list[tuple[float, list[tuple[float, float]]]] = []
    y_value = min_y
    while y_value <= max_y + 1e-6:
        segments = _segments_for_scanline(local_points, y_value)
        if segments:
            rows.append((y_value, segments))
        y_value += strip_spacing_m

    if not rows:
        mid_y = (min_y + max_y) / 2.0
        fallback = _segments_for_scanline(local_points, mid_y)
        if fallback:
            rows.append((mid_y, fallback))

    path_xy: list[tuple[float, float]] = []
    reverse_row = False
    for row_y, segments in rows:
        row_points: list[tuple[float, float]] = []
        for start_x, end_x in segments:
            sampled = _sample_segment(start_x, end_x, row_y, waypoint_spacing_m)
            if reverse_row:
                sampled.reverse()
            row_points.extend(sampled)
        if not row_points:
            continue
        if path_xy and path_xy[-1] == row_points[0]:
            row_points = row_points[1:]
        path_xy.extend(row_points)
        reverse_row = not reverse_row

    deduped: list[GeoPoint] = []
    for x_m, y_m in path_xy:
        point = unproject_local_m(x_m, y_m, reference.latitude_deg, reference.longitude_deg)
        if deduped and math.isclose(point.latitude_deg, deduped[-1].latitude_deg, abs_tol=1e-8) and math.isclose(
            point.longitude_deg, deduped[-1].longitude_deg, abs_tol=1e-8,
        ):
            continue
        deduped.append(point)
    return deduped


def _segments_for_scanline(
    polygon_xy: list[tuple[float, float]],
    y_value: float,
) -> list[tuple[float, float]]:
    intersections: list[float] = []
    point_count = len(polygon_xy)
    for index in range(point_count):
        x_a, y_a = polygon_xy[index]
        x_b, y_b = polygon_xy[(index + 1) % point_count]
        if math.isclose(y_a, y_b, abs_tol=1e-9):
            continue
        if y_value < min(y_a, y_b) or y_value >= max(y_a, y_b):
            continue
        ratio = (y_value - y_a) / (y_b - y_a)
        intersections.append(x_a + ratio * (x_b - x_a))
    intersections.sort()
    segments: list[tuple[float, float]] = []
    for index in range(0, len(intersections) - 1, 2):
        start_x = intersections[index]
        end_x = intersections[index + 1]
        if math.isclose(start_x, end_x, abs_tol=1e-9):
            continue
        segments.append((start_x, end_x))
    return segments


def _sample_segment(
    start_x: float,
    end_x: float,
    y_value: float,
    waypoint_spacing_m: float,
) -> list[tuple[float, float]]:
    distance_m = abs(end_x - start_x)
    if math.isclose(distance_m, 0.0, abs_tol=1e-9):
        return [(start_x, y_value)]

    steps = max(1, int(math.ceil(distance_m / waypoint_spacing_m)))
    delta = (end_x - start_x) / steps
    return [
        (start_x + delta * step_index, y_value)
        for step_index in range(steps + 1)
    ]
