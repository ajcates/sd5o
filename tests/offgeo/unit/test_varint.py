"""Unit tests for tools/offgeo/lib/varint.py (OFF-104, R1 Group D)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import varint  # noqa: E402


class UvarintTests(unittest.TestCase):
    def test_single_byte_values_round_trip(self):
        for v in (0, 1, 63, 127):
            encoded = varint.write_uvarint(v)
            self.assertEqual(len(encoded), 1)
            decoded, offset = varint.read_uvarint(encoded, 0)
            self.assertEqual(decoded, v)
            self.assertEqual(offset, len(encoded))

    def test_multi_byte_values_round_trip(self):
        for v in (128, 300, 16384, 10**9, 2**32 - 1):
            encoded = varint.write_uvarint(v)
            self.assertGreater(len(encoded), 1)
            decoded, offset = varint.read_uvarint(encoded, 0)
            self.assertEqual(decoded, v)
            self.assertEqual(offset, len(encoded))

    def test_negative_value_rejected(self):
        with self.assertRaises(ValueError):
            varint.write_uvarint(-1)

    def test_reads_from_a_nonzero_offset_and_leaves_the_rest_of_the_buffer_alone(self):
        buf = b"\xff" + varint.write_uvarint(300)
        decoded, offset = varint.read_uvarint(buf, 1)
        self.assertEqual(decoded, 300)
        self.assertEqual(offset, len(buf))


class ZigzagTests(unittest.TestCase):
    def test_small_magnitude_negatives_stay_small(self):
        # The whole point of zigzag: -1 should encode as small as +1, not
        # as a huge two's-complement value.
        self.assertEqual(varint.zigzag_encode(0), 0)
        self.assertEqual(varint.zigzag_encode(-1), 1)
        self.assertEqual(varint.zigzag_encode(1), 2)
        self.assertEqual(varint.zigzag_encode(-2), 3)
        self.assertEqual(varint.zigzag_encode(2), 4)

    def test_round_trips_including_large_magnitudes(self):
        for v in (0, 1, -1, 127, -127, 128, -128, 10**6, -10**6, 2**31 - 1, -(2**31)):
            self.assertEqual(varint.zigzag_decode(varint.zigzag_encode(v)), v)

    def test_svarint_negative_encodes_as_few_bytes_as_its_positive_counterpart(self):
        # A geometry coordinate delta of -5 must not cost more bytes than
        # +5 -- that's the whole reason this module exists instead of
        # just reusing write_uvarint on signed deltas directly.
        self.assertEqual(len(varint.write_svarint(-5)), len(varint.write_svarint(5)))

    def test_svarint_round_trip(self):
        for v in (0, -1, 1, -1000000, 1000000):
            encoded = varint.write_svarint(v)
            decoded, offset = varint.read_svarint(encoded, 0)
            self.assertEqual(decoded, v)
            self.assertEqual(offset, len(encoded))


if __name__ == "__main__":
    unittest.main()
