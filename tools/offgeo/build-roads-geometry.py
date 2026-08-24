#!/usr/bin/env python3
"""Extract a small roads-geometry basemap for the map prototype (see
build-address-index.py's docstring for the same "prototype, not the real
R1/R2 compiler" framing). No raster map tiles are used here at all --
bulk-mirroring the public OpenStreetMap tile server would violate its
usage policy, and self-rendering our own tiles is a heavier pipeline than
this prototype needs. Instead: draw the SanGIS Roads-All centerlines
directly, which are already pinned, licensed for this, and inherently a
"self-hosted" static asset.

Scope: rather than one whole-county bounding box (the 28 communities the
calls feed dispatches to are scattered across the county, so their
combined envelope is nearly the whole county and wouldn't cut file size
at all), this computes one small per-community bounding box from the
Address Points already used to build the address index, and keeps a road
segment only if its own bounding box overlaps *any* of those -- excluding
the large incorporated-city areas (San Diego, Chula Vista, Escondido
proper, etc.) sitting between the scattered communities we actually cover.
Geometry is simplified (Douglas-Peucker, in State Plane feet so units are
uniform) before the State Plane -> WGS84 transform.

Usage: python3 tools/offgeo/build-roads-geometry.py
Output: src/app/data/roads.json (checked in)
        build/offgeo-sources/roads-geometry-report.json (gitignored detail)
"""
from __future__ import annotations

import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import dbf  # noqa: E402
import shp  # noqa: E402
from coords import batch_state_plane_2230_feet_to_wgs84  # noqa: E402

LOCK_PATH = REPO_ROOT / "tools/offgeo/config/sources.lock.json"
CROSSWALK_PATH = REPO_ROOT / "tests/offgeo/fixtures/community-crosswalk.json"
OUTPUT_PATH = REPO_ROOT / "src/app/data/roads.json"
REPORT_PATH = REPO_ROOT / "build/offgeo-sources/roads-geometry-report.json"

BBOX_MARGIN_FT = 1500.0  # ~460m, enough to keep a little surrounding-street context
SIMPLIFY_TOLERANCE_FT = 35.0  # Douglas-Peucker tolerance, ~10.7m -- roads are visual context here, not a matching surface


def load_allowed_communities() -> set[str]:
    crosswalk = json.loads(CROSSWALK_PATH.read_text())
    allowed = set()
    for info in crosswalk["mappedCommunities"].values():
        for variant in info["sangisRawVariants"]:
            allowed.add(variant["raw"])
    return allowed


def compute_community_bboxes(allowed_communities: set[str]) -> list[tuple[float, float, float, float]]:
    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "sangis-address-points")
    path = REPO_ROOT / entry["retainedPath"]
    bounds: dict[str, list[float]] = defaultdict(lambda: [float("inf"), float("inf"), float("-inf"), float("-inf")])

    with zipfile.ZipFile(path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".dbf"))
        with zf.open(member) as stream:
            header, records = dbf.open_dbf(stream)
            for row in records:
                community = row["COMMUNITY"]
                if community not in allowed_communities:
                    continue
                try:
                    x, y = float(row["X_COORD"]), float(row["Y_COORD"])
                except ValueError:
                    continue
                if x == 0.0 and y == 0.0:
                    continue
                b = bounds[community]
                b[0] = min(b[0], x)
                b[1] = min(b[1], y)
                b[2] = max(b[2], x)
                b[3] = max(b[3], y)

    boxes = []
    for xmin, ymin, xmax, ymax in bounds.values():
        boxes.append((xmin - BBOX_MARGIN_FT, ymin - BBOX_MARGIN_FT, xmax + BBOX_MARGIN_FT, ymax + BBOX_MARGIN_FT))
    return boxes


def boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def perpendicular_distance(point, start, end) -> float:
    (px, py), (sx, sy), (ex, ey) = point, start, end
    if (sx, sy) == (ex, ey):
        return ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
    num = abs((ey - sy) * px - (ex - sx) * py + ex * sy - ey * sx)
    den = ((ey - sy) ** 2 + (ex - sx) ** 2) ** 0.5
    return num / den


def douglas_peucker(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    max_dist = 0.0
    index = 0
    for i in range(1, len(points) - 1):
        dist = perpendicular_distance(points[i], points[0], points[-1])
        if dist > max_dist:
            max_dist = dist
            index = i
    if max_dist > tolerance:
        left = douglas_peucker(points[: index + 1], tolerance)
        right = douglas_peucker(points[index:], tolerance)
        return left[:-1] + right
    return [points[0], points[-1]]


def main() -> None:
    allowed_communities = load_allowed_communities()
    print(f"Computing per-community bounding boxes for {len(allowed_communities)} SanGIS COMMUNITY values ...")
    community_boxes = compute_community_bboxes(allowed_communities)
    print(f"{len(community_boxes)} community bounding boxes (margin {BBOX_MARGIN_FT} ft).")

    lock = json.loads(LOCK_PATH.read_text())
    entry = next(e for e in lock["sources"] if e["id"] == "sangis-roads-all")
    path = REPO_ROOT / entry["retainedPath"]

    kept_parts: list[list[tuple[float, float]]] = []
    total_records = 0
    kept_records = 0

    with zipfile.ZipFile(path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".shp"))
        with zf.open(member) as stream:
            shp.read_header(stream)
            for bbox, parts in shp.iter_polylines(stream):
                total_records += 1
                if not parts:
                    continue
                if not any(boxes_overlap(bbox, cb) for cb in community_boxes):
                    continue
                kept_records += 1
                for part in parts:
                    simplified = douglas_peucker(part, SIMPLIFY_TOLERANCE_FT)
                    if len(simplified) >= 2:
                        kept_parts.append(simplified)

    raw_point_count = sum(len(p) for p in kept_parts)
    print(f"Scanned {total_records} road records, kept {kept_records} overlapping the scoped communities.")
    print(f"{len(kept_parts)} line parts, {raw_point_count} points after Douglas-Peucker simplification.")
    print("Transforming State Plane -> WGS84 via cs2cs ...")

    flat_points = [pt for part in kept_parts for pt in part]
    flat_coords = batch_state_plane_2230_feet_to_wgs84(flat_points)

    output_lines: list[list[list[float]]] = []
    cursor = 0
    for part in kept_parts:
        n = len(part)
        line = [[round(lat, 4), round(lon, 4)] for (lat, lon) in flat_coords[cursor : cursor + n]]
        cursor += n
        output_lines.append(line)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output_lines, separators=(",", ":")) + "\n")
    size_bytes = OUTPUT_PATH.stat().st_size

    report = {
        "communityBoundingBoxCount": len(community_boxes),
        "totalRoadRecords": total_records,
        "keptRoadRecords": kept_records,
        "outputLineCount": len(output_lines),
        "outputPointCount": raw_point_count,
        "simplifyToleranceFt": SIMPLIFY_TOLERANCE_FT,
        "outputBytes": size_bytes,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")

    print(f"Wrote {len(output_lines)} lines ({size_bytes / 1_000_000:.2f} MB) to {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
