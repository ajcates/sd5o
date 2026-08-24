"""State Plane (EPSG:2230, NAD83 / California zone 6, US survey feet) ->
WGS84 lat/lon, via PROJ's `cs2cs` CLI (Termux package `proj`).

Both pinned SanGIS sources (Roads-All, Address Points) use this exact CRS
(confirmed from each archive's .prj -- see tools/offgeo/README.md's CRS
control points section, OFF-014).

An earlier version of this module hand-implemented the two-standard-
-parallel Lambert Conformal Conic inverse projection directly (Snyder's
formulas). It had a real bug -- verified by comparing its output for a
sample Address Points row (611 W G ST, San Diego, X=6279119.9 Y=1840176.1
ft) against `cs2cs`: the hand-rolled version placed it in the Texas
panhandle (35.04, -101.92), about 1,400 km from the correct answer
(32.71225, -117.16857), which `cs2cs` confirms directly. Rather than debug
the projection algebra further, this module now shells out to `cs2cs`,
which is the standard, independently-verified tool for exactly this
transform. Batched via one subprocess call per dataset (~20,000
points/second measured on this device), not one process per point.

NAD83 and WGS84 are treated as equivalent here (PROJ's default EPSG:2230
-> EPSG:4326 pipeline does not apply a datum shift beyond the ellipsoid
change, which is standard practice at this accuracy budget -- the two
datums agree to within about a meter in California). An explicit,
versioned NAD83->WGS84 transform is still tracked as real future work
(spec.md Section 6.4), not silently assumed away.
"""
from __future__ import annotations

import subprocess


def batch_state_plane_2230_feet_to_wgs84(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """points: list of (x_ft, y_ft) in EPSG:2230 US survey feet.
    Returns a list of (lat, lon) in degrees, same order/length."""
    if not points:
        return []
    stdin_text = "\n".join(f"{x!r} {y!r}" for x, y in points)
    result = subprocess.run(
        ["cs2cs", "-f", "%.8f", "EPSG:2230", "EPSG:4326"],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=True,
    )
    out_lines = result.stdout.strip("\n").split("\n")
    if len(out_lines) != len(points):
        raise RuntimeError(f"cs2cs returned {len(out_lines)} lines for {len(points)} input points")
    coords = []
    for line in out_lines:
        lat_str, lon_str, _z = line.split()
        coords.append((float(lat_str), float(lon_str)))
    return coords


# San Diego County's approximate lat/lon bounds -- used to sanity-check
# transformed points, not as a strict clip.
SAN_DIEGO_COUNTY_BOUNDS = {"lat_min": 32.5, "lat_max": 33.55, "lon_min": -117.65, "lon_max": -116.0}


def is_plausible_san_diego_point(lat: float, lon: float) -> bool:
    b = SAN_DIEGO_COUNTY_BOUNDS
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]
