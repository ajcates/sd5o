"""Minimal streaming reader for the ESRI Shapefile .shp geometry format,
just enough to read PolyLine (shape type 3) and PolyLineZ (13) records --
that's what SanGIS Roads-All ships (confirmed type 13 by reading its
100-byte file header directly). Stdlib-only, same rationale as
tools/offgeo/lib/dbf.py: this is exploration/prototype tooling, not a
commitment to a shapefile library dependency (that's OFF-012).

Z and M values are read past (to keep the stream position correct for the
next record) but discarded -- the map prototype only needs 2D line
geometry to draw roads, not elevation.
"""
from __future__ import annotations

import struct
from typing import BinaryIO, Iterator

SHAPE_TYPE_POLYLINE = 3
SHAPE_TYPE_POLYLINE_Z = 13


def read_header(stream: BinaryIO) -> dict:
    raw = stream.read(100)
    if len(raw) < 100:
        raise ValueError("truncated .shp header")
    file_code = struct.unpack_from(">i", raw, 0)[0]
    if file_code != 9994:
        raise ValueError(f"not a shapefile (file code {file_code})")
    shape_type = struct.unpack_from("<i", raw, 32)[0]
    if shape_type not in (SHAPE_TYPE_POLYLINE, SHAPE_TYPE_POLYLINE_Z):
        raise ValueError(f"unsupported shape type {shape_type} -- only PolyLine/PolyLineZ are implemented")
    bbox = struct.unpack_from("<4d", raw, 36)
    return {"shapeType": shape_type, "bbox": bbox}


def iter_polylines(
    stream: BinaryIO,
) -> Iterator[tuple[tuple[float, float, float, float], list[list[tuple[float, float]]]]]:
    """Yield (bbox, parts) per record -- bbox is the record's own
    (xmin, ymin, xmax, ymax) as stored in the file (cheap overlap tests
    without needing to scan every point), parts is a list of point lists
    in the shapefile's native CRS (untransformed)."""
    while True:
        record_header = stream.read(8)
        if len(record_header) < 8:
            return  # end of file
        content_words = struct.unpack_from(">i", record_header, 4)[0]
        content_bytes = content_words * 2
        content = stream.read(content_bytes)
        if len(content) < content_bytes:
            return  # truncated tail; stop rather than raise

        shape_type = struct.unpack_from("<i", content, 0)[0]
        if shape_type == 0:  # null shape record
            yield (0.0, 0.0, 0.0, 0.0), []
            continue

        bbox = struct.unpack_from("<4d", content, 4)
        num_parts, num_points = struct.unpack_from("<ii", content, 36)
        offset = 44
        part_starts = struct.unpack_from(f"<{num_parts}i", content, offset)
        offset += 4 * num_parts
        xy = struct.unpack_from(f"<{num_points * 2}d", content, offset)

        parts: list[list[tuple[float, float]]] = []
        for i, start in enumerate(part_starts):
            end = part_starts[i + 1] if i + 1 < num_parts else num_points
            part = [(xy[2 * j], xy[2 * j + 1]) for j in range(start, end)]
            parts.append(part)
        yield bbox, parts
