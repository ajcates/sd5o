"""Unit tests for tools/offgeo/lib/interpolate.py (OFF-105, R1 Group D)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import interpolate  # noqa: E402


class HaversineTests(unittest.TestCase):
    def test_same_point_is_zero_distance(self):
        self.assertAlmostEqual(interpolate.haversine_meters(32.71225, -117.16857, 32.71225, -117.16857), 0.0)

    def test_known_short_distance_is_plausible(self):
        # 611 W G St and 1500 El Prado (Balboa Park), both real SanGIS
        # control points from OFF-014 -- roughly 2.3 km apart in reality.
        d = interpolate.haversine_meters(32.71225, -117.16857, 32.73187, -117.14959)
        self.assertGreater(d, 2000)
        self.assertLess(d, 3000)


class PolylineLengthTests(unittest.TestCase):
    def test_two_point_line_matches_haversine(self):
        points = [(32.0, -117.0), (32.001, -117.001)]
        length = interpolate.polyline_length_meters(points)
        expected = interpolate.haversine_meters(*points[0], *points[1])
        self.assertAlmostEqual(length, expected, delta=expected * 0.01)

    def test_single_point_has_zero_length(self):
        self.assertEqual(interpolate.polyline_length_meters([(32.0, -117.0)]), 0.0)

    def test_multi_vertex_length_is_sum_of_segments(self):
        points = [(32.0, -117.0), (32.001, -117.0), (32.001, -117.001)]
        total = interpolate.polyline_length_meters(points)
        a = interpolate.polyline_length_meters(points[0:2])
        b = interpolate.polyline_length_meters(points[1:3])
        self.assertAlmostEqual(total, a + b, delta=0.01)


class InterpolateAlongPolylineTests(unittest.TestCase):
    def test_fraction_zero_returns_first_vertex(self):
        points = [(32.0, -117.0), (32.01, -117.01)]
        self.assertEqual(interpolate.interpolate_along_polyline(points, 0.0), points[0])

    def test_fraction_one_returns_last_vertex(self):
        points = [(32.0, -117.0), (32.01, -117.01)]
        got = interpolate.interpolate_along_polyline(points, 1.0)
        self.assertAlmostEqual(got[0], points[-1][0], places=6)
        self.assertAlmostEqual(got[1], points[-1][1], places=6)

    def test_fraction_half_on_straight_line_is_the_midpoint(self):
        points = [(32.0, -117.0), (32.01, -117.0)]  # due north, constant longitude
        lat, lon = interpolate.interpolate_along_polyline(points, 0.5)
        self.assertAlmostEqual(lat, 32.005, places=4)
        self.assertAlmostEqual(lon, -117.0, places=6)

    def test_fraction_is_clamped_below_zero_and_above_one(self):
        points = [(32.0, -117.0), (32.01, -117.01)]
        self.assertEqual(
            interpolate.interpolate_along_polyline(points, -0.5),
            interpolate.interpolate_along_polyline(points, 0.0),
        )
        self.assertEqual(
            interpolate.interpolate_along_polyline(points, 1.5),
            interpolate.interpolate_along_polyline(points, 1.0),
        )

    def test_zero_length_polyline_returns_first_vertex_without_raising(self):
        points = [(32.0, -117.0), (32.0, -117.0), (32.0, -117.0)]
        self.assertEqual(interpolate.interpolate_along_polyline(points, 0.7), points[0])

    def test_single_vertex_polyline_always_returns_that_vertex(self):
        points = [(32.0, -117.0)]
        self.assertEqual(interpolate.interpolate_along_polyline(points, 0.3), points[0])

    def test_multi_vertex_walk_lands_in_the_correct_segment(self):
        # Three equal-length segments (roughly) -- fraction 0.5 should
        # land inside the middle segment, not snap to a vertex.
        points = [(32.000, -117.000), (32.001, -117.000), (32.002, -117.000), (32.003, -117.000)]
        lat, lon = interpolate.interpolate_along_polyline(points, 0.5)
        self.assertGreater(lat, 32.001)
        self.assertLess(lat, 32.002)


class RangeFractionTests(unittest.TestCase):
    def test_low_end_is_zero(self):
        self.assertEqual(interpolate.range_fraction(100, 100, 200), 0.0)

    def test_high_end_is_one(self):
        self.assertEqual(interpolate.range_fraction(200, 100, 200), 1.0)

    def test_midpoint_is_half(self):
        self.assertEqual(interpolate.range_fraction(150, 100, 200), 0.5)

    def test_descending_range_still_produces_a_sensible_fraction(self):
        # low > high (the one real descending-range segment OFF-103
        # profiling found) -- the formula must still place the number
        # correctly along the FROM->TO direction the range describes,
        # not just for the common ascending case.
        self.assertEqual(interpolate.range_fraction(75, 100, 50), 0.5)
        self.assertEqual(interpolate.range_fraction(100, 100, 50), 0.0)
        self.assertEqual(interpolate.range_fraction(50, 100, 50), 1.0)

    def test_zero_width_range_returns_none(self):
        self.assertIsNone(interpolate.range_fraction(100, 100, 100))


if __name__ == "__main__":
    unittest.main()
