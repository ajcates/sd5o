"""Unit tests for tools/offgeo/lib/coords.py (OFF-012, Group 6).

test_known_address_regression pins down the exact 611 W G St, San Diego
bug the map-prototype work found by hand (see coords.py's own docstring
and notes/offgeo/map-prototype.md): a hand-rolled Lambert Conformal Conic
inverse placed this point ~1,400 km away in the Texas panhandle. This
test fails loudly if a future edit to the cs2cs invocation (wrong EPSG
codes, wrong argument order, wrong axis) regresses that same way again.
Skipped automatically if `cs2cs` isn't installed on the running host.
"""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import coords  # noqa: E402

HAS_CS2CS = shutil.which("cs2cs") is not None


class PlausibilityTests(unittest.TestCase):
    def test_known_good_point_is_plausible(self):
        self.assertTrue(coords.is_plausible_san_diego_point(32.71225, -117.16857))

    def test_texas_panhandle_bug_value_is_rejected(self):
        # The exact wrong output the old hand-rolled projection produced.
        self.assertFalse(coords.is_plausible_san_diego_point(35.04, -101.92))

    def test_zero_sentinel_is_rejected(self):
        self.assertFalse(coords.is_plausible_san_diego_point(0.0, 0.0))


@unittest.skipUnless(HAS_CS2CS, "cs2cs (PROJ) is not installed on this host")
class TransformTests(unittest.TestCase):
    def test_known_address_regression(self):
        # 611 W G St, San Diego -- EPSG:2230 State Plane feet from a real
        # SanGIS Address Points row, and its independently-known WGS84
        # location.
        lat, lon = coords.batch_state_plane_2230_feet_to_wgs84([(6279119.9, 1840176.1)])[0]
        self.assertAlmostEqual(lat, 32.71225, delta=0.001)
        self.assertAlmostEqual(lon, -117.16857, delta=0.001)
        self.assertTrue(coords.is_plausible_san_diego_point(lat, lon))

    def test_empty_input_returns_empty_output(self):
        self.assertEqual(coords.batch_state_plane_2230_feet_to_wgs84([]), [])

    def test_batch_preserves_order_and_count(self):
        points = [(6279119.9, 1840176.1), (6279119.9, 1840176.1)]
        result = coords.batch_state_plane_2230_feet_to_wgs84(points)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], result[1])


if __name__ == "__main__":
    unittest.main()
