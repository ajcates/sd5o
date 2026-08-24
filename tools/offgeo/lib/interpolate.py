"""Polyline-length, polyline-interpolation, and great-circle distance
helpers (`OFF-105`, R1 Group D). Stdlib `math` only.

`haversine_meters` is the accurate distance function, used for the
final ground-truth accuracy check in `prototype-benchmark-reader.py`
(comparing an interpolated point against a real address point's
surveyed coordinate). `_planar_meters` is a fast equirectangular
approximation used internally by the length/interpolation walk, which
only ever operates over a single road segment's own extent (tens to a
few hundred meters) -- accurate to well under 0.1% error at that scale,
not a substitute for `haversine_meters` at longer distances.
"""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6371000.0


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _planar_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat_avg = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lon2 - lon1) * math.cos(lat_avg) * EARTH_RADIUS_M
    dy = math.radians(lat2 - lat1) * EARTH_RADIUS_M
    return math.hypot(dx, dy)


def polyline_length_meters(points: list[tuple[float, float]]) -> float:
    """points: list of (lat, lon). Sum of consecutive-vertex distances."""
    return sum(_planar_meters(*points[i], *points[i + 1]) for i in range(len(points) - 1))


def interpolate_along_polyline(points: list[tuple[float, float]], fraction: float) -> tuple[float, float]:
    """Walk `points` (lat, lon) from the first vertex toward the last,
    returning the point at `fraction` (clamped to [0, 1]) of the total
    polyline length. A single-vertex polyline always returns that vertex.
    A zero-length polyline (all vertices coincide) returns the first
    vertex, same as fraction=0 would, rather than dividing by zero."""
    fraction = max(0.0, min(1.0, fraction))
    if len(points) == 1:
        return points[0]
    total = polyline_length_meters(points)
    if total == 0:
        return points[0]
    target = fraction * total
    covered = 0.0
    for i in range(len(points) - 1):
        lat1, lon1 = points[i]
        lat2, lon2 = points[i + 1]
        seg_len = _planar_meters(lat1, lon1, lat2, lon2)
        if covered + seg_len >= target or i == len(points) - 2:
            remaining = target - covered
            t = 0.0 if seg_len == 0 else min(1.0, remaining / seg_len)
            return (lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)
        covered += seg_len
    return points[-1]


def range_fraction(house_number: float, low: int, high: int) -> float | None:
    """Where `house_number` falls between `low` and `high` as a 0..1
    fraction. Direction-agnostic: works the same whether `low < high`
    (ascending, the common case) or `low > high` (descending -- one
    real segment found in OFF-103 profiling) since `(v - low) /
    (high - low)` is algebraically symmetric either way. Returns None
    only for a degenerate zero-width range (`low == high`), which the
    caller must handle (e.g. by using the segment midpoint) since there
    is no meaningful fraction to compute."""
    if high == low:
        return None
    return (house_number - low) / (high - low)
