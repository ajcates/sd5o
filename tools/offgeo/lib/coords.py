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

That future work is `batch_nad83_geographic_to_wgs84` below, added when
the Census ADDRFEAT reader needed it (its source CRS is geographic NAD83,
EPSG:4269 -- confirmed from its own .prj -- not State Plane feet).
Checked directly with `projinfo -s EPSG:4269 -t EPSG:4326
--hide-ballpark`: PROJ's *default* `cs2cs EPSG:4269 EPSG:4326` operation
is a "Ballpark geographic offset from NAD83 to WGS 84" (`+proj=noop`,
literally zero shift, "unknown accuracy") -- i.e. `cs2cs` with a bare
CRS pair would have done exactly the silent NAD83-as-WGS84 relabeling
spec.md 6.1 warns against, not caught by inspection since the numbers
still look plausible. The real, accuracy-graded operation for San Diego
County (EPSG operation 1750 / "NAD83 to WGS 84 (54)", 2.0 m, "California
south of 36.5 degrees N") requires the NOAA `us_noaa_cshpgn.tif`
HARN/NADCON grid (~6.8 KB), which PROJ does not ship by default and must
be fetched once via `projsync --file us_noaa_cshpgn.tif` (cached under
PROJ's user data dir, typically `~/.local/share/proj`). Measured against
the known-good 611 W G St control point: the ballpark no-op returns the
input unchanged to the printed precision, while the real grid shifts it
by about 0.135 m in latitude and negligibly in longitude -- small, but a
real, sourced, non-zero shift instead of a silent identity.
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


# EPSG operation 1750 realized as an explicit PROJ pipeline (rather than
# relying on `cs2cs EPSG:4269 EPSG:4326` picking it, since that command
# form ranks the ballpark no-op above it by default) -- steps verbatim
# from `projinfo -s EPSG:4269 -t EPSG:4326 --hide-ballpark --spatial-test
# intersects -o PROJ` operation 4, "NAD83 to WGS 84 (54)". Scoped to
# Southern California (San Diego County is entirely south of 36.5degN);
# a Northern California ADDRFEAT extract would need `us_noaa_cnhpgn.tif`
# instead, out of scope for this project's single-county source.
NAD83_TO_WGS84_SOCAL_PIPELINE = [
    "+proj=pipeline",
    "+step", "+proj=axisswap", "+order=2,1",
    "+step", "+proj=unitconvert", "+xy_in=deg", "+xy_out=rad",
    "+step", "+proj=hgridshift", "+grids=us_noaa_cshpgn.tif",
    "+step", "+proj=unitconvert", "+xy_in=rad", "+xy_out=deg",
    "+step", "+proj=axisswap", "+order=2,1",
]


def batch_nad83_geographic_to_wgs84(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """points: list of (lat, lon) in EPSG:4269 (NAD83) degrees -- the
    axis order EPSG:4269 officially defines (latitude first), matching
    what this function's own pipeline's leading `axisswap` expects.
    Returns a list of (lat, lon) in WGS84 degrees, same order/length.

    Uses PROJ's `cct` (coordinate conversion tool), not `cs2cs`, because
    `cs2cs` only accepts a source/target CRS pair and picks whichever
    operation PROJ ranks highest for that pair -- which is the ballpark
    no-op described in this module's top docstring, not the grid-based
    one this function exists to force. `cct` accepts an explicit pipeline
    instead, so there's no ranking step that could silently prefer the
    no-op.

    Raises (via `subprocess.run(..., check=True)`) if `us_noaa_cshpgn.tif`
    isn't present locally -- see this module's top docstring for how to
    fetch it. Deliberately does not fall back to the ballpark transform
    on a missing grid; a loud failure here is much cheaper than a
    silently-under-accurate Census-derived coordinate shipped downstream.
    """
    if not points:
        return []
    # cct (unlike cs2cs) silently drops a final line with no trailing
    # newline rather than processing it -- confirmed directly by testing
    # a single-point input with and without one. Always terminate with \n.
    stdin_text = "".join(f"{lat!r} {lon!r} 0 0\n" for lat, lon in points)
    result = subprocess.run(
        ["cct", *NAD83_TO_WGS84_SOCAL_PIPELINE],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=True,
    )
    out_lines = [line for line in result.stdout.strip("\n").split("\n") if line.strip()]
    if len(out_lines) != len(points):
        raise RuntimeError(
            f"cct returned {len(out_lines)} usable lines for {len(points)} input points "
            f"-- likely a per-record transformation error (points outside the grid's coverage?); "
            f"stderr: {result.stderr.strip()}"
        )
    coords = []
    for line in out_lines:
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("#"):
            raise RuntimeError(f"cct returned an unexpected line, refusing to guess: {line!r}")
        coords.append((float(parts[0]), float(parts[1])))
    return coords


# San Diego County's approximate lat/lon bounds -- used to sanity-check
# transformed points, not as a strict clip.
SAN_DIEGO_COUNTY_BOUNDS = {"lat_min": 32.5, "lat_max": 33.55, "lon_min": -117.65, "lon_max": -116.0}


def is_plausible_san_diego_point(lat: float, lon: float) -> bool:
    b = SAN_DIEGO_COUNTY_BOUNDS
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]
