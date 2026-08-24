"""Unit tests for tools/offgeo/lib/packformat.py (OFF-104/OFF-105, R1
Group D). Exercises the codec directly on small synthetic records --
prototype-pack-formats.py separately round-trip-verifies it against all
164,555 real road records, which this suite doesn't duplicate.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import packformat  # noqa: E402


def make_record(**overrides) -> dict:
    record = {
        "roadsegid": 1,
        "pdir": None,
        "name": "MAIN",
        "postd": None,
        "sfx": "STREET",
        "lLow": 100, "lHigh": 198, "rLow": 101, "rHigh": 199,
        "lMix": False, "rMix": False,
        "confidence": "ORDINARY",
        "leftZip": "92101", "rightZip": "92101",
        "points": [(32.71225, -117.16857), (32.71300, -117.16900)],
    }
    record.update(overrides)
    return record


class RoundTripTests(unittest.TestCase):
    def test_single_record_round_trips_exactly(self):
        records = [make_record()]
        blob = packformat.encode_records(records)
        decoded = packformat.decode_records(blob)
        self.assertEqual(len(decoded), 1)
        got = decoded[0]
        self.assertEqual(got["roadsegid"], 1)
        self.assertEqual(got["name"], "MAIN")
        self.assertEqual(got["sfx"], "STREET")
        self.assertIsNone(got["pdir"])
        self.assertEqual((got["lLow"], got["lHigh"], got["rLow"], got["rHigh"]), (100, 198, 101, 199))
        self.assertFalse(got["lMix"])
        self.assertFalse(got["rMix"])
        self.assertEqual(got["confidence"], "ORDINARY")
        self.assertEqual(got["leftZip"], "92101")
        self.assertEqual(got["rightZip"], "92101")

    def test_geometry_round_trips_within_coord_scale_precision(self):
        records = [make_record()]
        decoded = packformat.decode_records(packformat.encode_records(records))
        for (olat, olon), (glat, glon) in zip(records[0]["points"], decoded[0]["points"]):
            self.assertAlmostEqual(olat, glat, delta=1 / packformat.COORD_SCALE)
            self.assertAlmostEqual(olon, glon, delta=1 / packformat.COORD_SCALE)

    def test_all_directions_and_confidences_round_trip(self):
        records = [
            make_record(roadsegid=i, pdir=pdir, postd=postd, confidence=conf)
            for i, (pdir, postd, conf) in enumerate(
                (d, d2, c)
                for d in packformat.DIRECTION_CODES
                for d2 in packformat.DIRECTION_CODES
                for c in packformat.CONFIDENCE_CODES
            )
        ]
        decoded = packformat.decode_records(packformat.encode_records(records))
        for original, got in zip(records, decoded):
            self.assertEqual(original["pdir"], got["pdir"])
            self.assertEqual(original["postd"], got["postd"])
            self.assertEqual(original["confidence"], got["confidence"])

    def test_blank_name_and_none_optional_fields_round_trip(self):
        records = [make_record(sfx=None, leftZip=None, rightZip=None)]
        decoded = packformat.decode_records(packformat.encode_records(records))
        self.assertIsNone(decoded[0]["sfx"])
        self.assertIsNone(decoded[0]["leftZip"])
        self.assertIsNone(decoded[0]["rightZip"])

    def test_mix_flags_round_trip_independently(self):
        records = [make_record(lMix=True, rMix=False), make_record(roadsegid=2, lMix=False, rMix=True)]
        decoded = packformat.decode_records(packformat.encode_records(records))
        self.assertEqual((decoded[0]["lMix"], decoded[0]["rMix"]), (True, False))
        self.assertEqual((decoded[1]["lMix"], decoded[1]["rMix"]), (False, True))

    def test_shared_geometry_is_deduplicated(self):
        shared_points = [(32.0, -117.0), (32.1, -117.1)]
        records = [make_record(roadsegid=1, points=shared_points), make_record(roadsegid=2, points=shared_points)]
        blob = packformat.encode_records(records)
        blob_with_distinct_geometry = packformat.encode_records(
            [make_record(roadsegid=1, points=shared_points), make_record(roadsegid=2, points=[(1.0, 1.0), (2.0, 2.0)])]
        )
        # Two records sharing identical geometry must produce a smaller
        # blob than two records with distinct geometry -- proves the
        # geometry table is actually deduplicating, not just decodable.
        self.assertLess(len(blob), len(blob_with_distinct_geometry))

    def test_empty_records_list_round_trips(self):
        self.assertEqual(packformat.decode_records(packformat.encode_records([])), [])


class MalformedInputTests(unittest.TestCase):
    def test_wrong_magic_is_rejected(self):
        blob = packformat.encode_records([make_record()])
        corrupted = b"XXXX" + blob[4:]
        with self.assertRaises(ValueError):
            packformat.decode_records(corrupted)

    def test_unsupported_version_is_rejected(self):
        blob = packformat.encode_records([make_record()])
        corrupted = blob[:4] + bytes([99]) + blob[5:]
        with self.assertRaises(ValueError):
            packformat.decode_records(corrupted)


if __name__ == "__main__":
    unittest.main()
