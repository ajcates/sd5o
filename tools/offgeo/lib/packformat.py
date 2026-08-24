"""Custom binary block-format codec (`OFF-104`/`OFF-105`, R1 Group D).

This is the reusable core originally built for
`tools/offgeo/prototype-pack-formats.py`'s whole-file custom-format
candidate, extracted here so `prototype-benchmark-reader.py` (`OFF-105`)
can reuse the *identical, already round-trip-verified* codec at block
granularity instead of a second hand-copied implementation that could
drift from it. `encode_records`/`decode_records` operate on an arbitrary
list of records -- callers decide whether that list is "the whole file"
(one block) or one street-key-aligned partition (many blocks); the codec
itself doesn't know or care which.

Record shape (both directions): a dict with keys `roadsegid`, `pdir`,
`name`, `postd`, `sfx`, `lLow`, `lHigh`, `rLow`, `rHigh`, `lMix`, `rMix`,
`confidence`, `leftZip`, `rightZip`, `points` (list of `(lat, lon)`
tuples) -- exactly what `compile-sangis-roads.py`'s reader output maps
onto (see `prototype-pack-formats.py::load_records`).
"""
from __future__ import annotations

import struct

try:
    # Scripts put tools/offgeo/lib directly on sys.path and import this
    # module flat (e.g. `import packformat`) -- see compile-sangis-roads.py.
    from varint import read_svarint, read_uvarint, write_svarint, write_uvarint
except ImportError:
    # Tests put tools/offgeo on sys.path and import via `from lib import
    # packformat` (see tests/offgeo/unit/test_coords.py's pattern) -- in
    # that mode this module needs the package-relative form instead.
    from .varint import read_svarint, read_uvarint, write_svarint, write_uvarint

COORD_SCALE = 1_000_000  # 6 decimal degrees, ~0.11 m at this latitude
MAGIC = b"OGP0"  # OffGeo Prototype format 0 -- NOT "OFG1" (roadmap.md reserves that name for the real R1 decision)
FORMAT_VERSION = 0

DIRECTION_CODES = [None, "N", "S", "E", "W", "NE", "NW", "SE", "SW"]
DIRECTION_TO_CODE = {d: i for i, d in enumerate(DIRECTION_CODES)}

CONFIDENCE_CODES = {"ORDINARY": 0, "FALLBACK": 1, "EXCLUDED": 2}
CONFIDENCE_BY_CODE = {v: k for k, v in CONFIDENCE_CODES.items()}


def encode_records(records: list[dict]) -> bytes:
    strings: list[str] = sorted(
        {r["name"] for r in records if r["name"]}
        | {r["sfx"] for r in records if r["sfx"]}
        | {r["leftZip"] for r in records if r["leftZip"]}
        | {r["rightZip"] for r in records if r["rightZip"]}
    )
    string_index = {s: i for i, s in enumerate(strings)}

    geometry_index: dict[tuple, int] = {}
    geometry_table: list[list[tuple[int, int]]] = []
    record_geometry_idx = []
    for r in records:
        scaled = tuple((round(lat * COORD_SCALE), round(lon * COORD_SCALE)) for lat, lon in r["points"])
        idx = geometry_index.get(scaled)
        if idx is None:
            idx = len(geometry_table)
            geometry_index[scaled] = idx
            geometry_table.append(list(scaled))
        record_geometry_idx.append(idx)

    strings_blob = bytearray()
    strings_blob += write_uvarint(len(strings))
    for s in strings:
        encoded = s.encode("utf-8")
        strings_blob += write_uvarint(len(encoded))
        strings_blob += encoded

    geometry_blob = bytearray()
    geometry_blob += write_uvarint(len(geometry_table))
    for points in geometry_table:
        geometry_blob += write_uvarint(len(points))
        prev_lat, prev_lon = 0, 0
        for lat, lon in points:
            geometry_blob += write_svarint(lat - prev_lat)
            geometry_blob += write_svarint(lon - prev_lon)
            prev_lat, prev_lon = lat, lon

    records_blob = bytearray()
    records_blob += write_uvarint(len(records))
    for r, geom_idx in zip(records, record_geometry_idx):
        records_blob += write_uvarint(r["roadsegid"])
        records_blob += write_uvarint(string_index[r["name"]] + 1 if r["name"] else 0)
        records_blob.append(DIRECTION_TO_CODE[r["pdir"]])
        records_blob.append(DIRECTION_TO_CODE[r["postd"]])
        records_blob += write_uvarint(string_index[r["sfx"]] + 1 if r["sfx"] else 0)
        records_blob += write_uvarint(r["lLow"])
        records_blob += write_uvarint(r["lHigh"])
        records_blob += write_uvarint(r["rLow"])
        records_blob += write_uvarint(r["rHigh"])
        flags = (1 if r["lMix"] else 0) | (2 if r["rMix"] else 0) | (CONFIDENCE_CODES[r["confidence"]] << 2)
        records_blob.append(flags)
        records_blob += write_uvarint(string_index[r["leftZip"]] + 1 if r["leftZip"] else 0)
        records_blob += write_uvarint(string_index[r["rightZip"]] + 1 if r["rightZip"] else 0)
        records_blob += write_uvarint(geom_idx)

    header = MAGIC + struct.pack("<B", FORMAT_VERSION)
    header += write_uvarint(len(strings_blob))
    header += write_uvarint(len(geometry_blob))
    header += write_uvarint(len(records_blob))

    return bytes(header) + bytes(strings_blob) + bytes(geometry_blob) + bytes(records_blob)


def decode_records(blob: bytes) -> list[dict]:
    if blob[:4] != MAGIC:
        raise ValueError("bad magic")
    version = blob[4]
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported version {version}")
    offset = 5
    strings_len, offset = read_uvarint(blob, offset)
    geometry_len, offset = read_uvarint(blob, offset)
    records_len, offset = read_uvarint(blob, offset)

    strings_start = offset
    geometry_start = strings_start + strings_len
    records_start = geometry_start + geometry_len

    o = strings_start
    n_strings, o = read_uvarint(blob, o)
    strings = []
    for _ in range(n_strings):
        slen, o = read_uvarint(blob, o)
        strings.append(blob[o : o + slen].decode("utf-8"))
        o += slen
    assert o == geometry_start

    o = geometry_start
    n_geoms, o = read_uvarint(blob, o)
    geometry_table = []
    for _ in range(n_geoms):
        n_points, o = read_uvarint(blob, o)
        points = []
        prev_lat = prev_lon = 0
        for _ in range(n_points):
            dlat, o = read_svarint(blob, o)
            dlon, o = read_svarint(blob, o)
            prev_lat += dlat
            prev_lon += dlon
            points.append((prev_lat / COORD_SCALE, prev_lon / COORD_SCALE))
        geometry_table.append(points)
    assert o == records_start

    o = records_start
    n_records, o = read_uvarint(blob, o)
    out = []
    for _ in range(n_records):
        roadsegid, o = read_uvarint(blob, o)
        name_idx, o = read_uvarint(blob, o)
        pdir_code = blob[o]; o += 1
        postd_code = blob[o]; o += 1
        sfx_idx, o = read_uvarint(blob, o)
        l_low, o = read_uvarint(blob, o)
        l_high, o = read_uvarint(blob, o)
        r_low, o = read_uvarint(blob, o)
        r_high, o = read_uvarint(blob, o)
        flags = blob[o]; o += 1
        left_zip_idx, o = read_uvarint(blob, o)
        right_zip_idx, o = read_uvarint(blob, o)
        geom_idx, o = read_uvarint(blob, o)
        out.append(
            {
                "roadsegid": roadsegid,
                "name": strings[name_idx - 1] if name_idx else "",
                "pdir": DIRECTION_CODES[pdir_code],
                "postd": DIRECTION_CODES[postd_code],
                "sfx": strings[sfx_idx - 1] if sfx_idx else None,
                "lLow": l_low, "lHigh": l_high, "rLow": r_low, "rHigh": r_high,
                "lMix": bool(flags & 1), "rMix": bool(flags & 2),
                "confidence": CONFIDENCE_BY_CODE[flags >> 2],
                "leftZip": strings[left_zip_idx - 1] if left_zip_idx else None,
                "rightZip": strings[right_zip_idx - 1] if right_zip_idx else None,
                "points": geometry_table[geom_idx],
            }
        )
    assert o == len(blob)
    return out
