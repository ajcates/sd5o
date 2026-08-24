"""Unit tests for tools/offgeo/lib/shp.py against small hand-built .shp
byte buffers (OFF-012, Group 6) -- previously only exercised against the
real 164,555-record SanGIS Roads-All archive."""
import io
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import shp  # noqa: E402


def build_shp_header(shape_type, bbox=(0.0, 0.0, 0.0, 0.0)):
    header = bytearray(100)
    struct.pack_into(">i", header, 0, 9994)  # file code
    struct.pack_into("<i", header, 32, shape_type)
    struct.pack_into("<4d", header, 36, *bbox)
    return bytes(header)


def build_polyline_record(record_number, bbox, parts):
    """parts: list of list of (x, y) points."""
    num_parts = len(parts)
    num_points = sum(len(p) for p in parts)
    part_starts = []
    running = 0
    for part in parts:
        part_starts.append(running)
        running += len(part)
    flat_points = [pt for part in parts for pt in part]

    content = bytearray()
    content += struct.pack("<i", 3)  # shape type: PolyLine
    content += struct.pack("<4d", *bbox)
    content += struct.pack("<ii", num_parts, num_points)
    content += struct.pack(f"<{num_parts}i", *part_starts)
    for x, y in flat_points:
        content += struct.pack("<2d", x, y)

    content_words = len(content) // 2
    record_header = struct.pack(">ii", record_number, content_words)
    return record_header + bytes(content)


class ShpTests(unittest.TestCase):
    def test_header_accepts_polyline(self):
        blob = build_shp_header(shp.SHAPE_TYPE_POLYLINE, bbox=(-1.0, -2.0, 3.0, 4.0))
        header = shp.read_header(io.BytesIO(blob))
        self.assertEqual(header["shapeType"], 3)
        self.assertEqual(header["bbox"], (-1.0, -2.0, 3.0, 4.0))

    def test_header_rejects_non_shapefile(self):
        bad = bytearray(100)
        struct.pack_into(">i", bad, 0, 1234)
        with self.assertRaises(ValueError):
            shp.read_header(io.BytesIO(bytes(bad)))

    def test_header_rejects_unsupported_shape_type(self):
        blob = build_shp_header(shape_type=5)  # Polygon, not implemented
        with self.assertRaises(ValueError):
            shp.read_header(io.BytesIO(blob))

    def test_single_part_polyline_roundtrips(self):
        points = [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)]
        record = build_polyline_record(1, (0.0, 0.0, 2.0, 1.0), [points])
        results = list(shp.iter_polylines(io.BytesIO(record)))
        self.assertEqual(len(results), 1)
        bbox, parts = results[0]
        self.assertEqual(bbox, (0.0, 0.0, 2.0, 1.0))
        self.assertEqual(parts, [points])

    def test_multi_part_polyline_splits_correctly(self):
        part_a = [(0.0, 0.0), (1.0, 0.0)]
        part_b = [(5.0, 5.0), (6.0, 6.0), (7.0, 5.0)]
        record = build_polyline_record(2, (0.0, 0.0, 7.0, 6.0), [part_a, part_b])
        results = list(shp.iter_polylines(io.BytesIO(record)))
        self.assertEqual(len(results), 1)
        _bbox, parts = results[0]
        self.assertEqual(parts, [part_a, part_b])

    def test_multiple_records_stream_in_order(self):
        rec1 = build_polyline_record(1, (0, 0, 1, 1), [[(0.0, 0.0), (1.0, 1.0)]])
        rec2 = build_polyline_record(2, (2, 2, 3, 3), [[(2.0, 2.0), (3.0, 3.0)]])
        results = list(shp.iter_polylines(io.BytesIO(rec1 + rec2)))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][1], [[(0.0, 0.0), (1.0, 1.0)]])
        self.assertEqual(results[1][1], [[(2.0, 2.0), (3.0, 3.0)]])


if __name__ == "__main__":
    unittest.main()
