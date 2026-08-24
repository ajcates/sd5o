"""Unit tests for tools/offgeo/lib/coords.py (OFF-012, Group 6; landmark
control points added for OFF-014).

test_known_landmarks_transform_correctly checks three real SanGIS address
points, geographically spread across the county (downtown, Balboa Park,
La Jolla), against their independently-known WGS84 locations. The first
one pins down the exact 611 W G St, San Diego bug the map-prototype work
found by hand (see coords.py's own docstring and
notes/offgeo/map-prototype.md): a hand-rolled Lambert Conformal Conic
inverse placed this point ~1,400 km away in the Texas panhandle. All
three fail loudly if a future edit to the cs2cs invocation (wrong EPSG
codes, wrong argument order, wrong axis) regresses that same way again --
the geographic spread means a wrong axis order or wrong zone would move
at least one of them by a lot more than the assertion tolerance, not just
611 W G St. Skipped automatically if `cs2cs` isn't installed on the host.
"""
import shutil
import sys
import unittest
import unittest.mock
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


# Real SanGIS Address Points rows (State Plane EPSG:2230 feet, from the
# retained sangis-address-points archive), each independently plausible
# against its well-known real-world location. See tools/offgeo/README.md's
# CRS control points (OFF-014) section for the same table.
KNOWN_LANDMARKS = [
    ("611 W G St, San Diego (downtown)", (6279119.9, 1840176.1), (32.71225, -117.16857)),
    ("1500 El Prado, Balboa Park", (6285018.6415, 1847261.2475), (32.73187, -117.14959)),
    ("7600 Girard Ave, La Jolla Village", (6247331.5175, 1887762.38825), (32.84222, -117.27342)),
]


@unittest.skipUnless(HAS_CS2CS, "cs2cs (PROJ) is not installed on this host")
class TransformTests(unittest.TestCase):
    def test_known_landmarks_transform_correctly(self):
        for label, state_plane_ft, expected_wgs84 in KNOWN_LANDMARKS:
            with self.subTest(landmark=label):
                lat, lon = coords.batch_state_plane_2230_feet_to_wgs84([state_plane_ft])[0]
                expected_lat, expected_lon = expected_wgs84
                self.assertAlmostEqual(lat, expected_lat, delta=0.001)
                self.assertAlmostEqual(lon, expected_lon, delta=0.001)
                self.assertTrue(coords.is_plausible_san_diego_point(lat, lon))

    def test_empty_input_returns_empty_output(self):
        self.assertEqual(coords.batch_state_plane_2230_feet_to_wgs84([]), [])

    def test_batch_preserves_order_and_count(self):
        points = [(6279119.9, 1840176.1), (6279119.9, 1840176.1)]
        result = coords.batch_state_plane_2230_feet_to_wgs84(points)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], result[1])


def _grid_available() -> bool:
    """`us_noaa_cshpgn.tif` isn't bundled with PROJ; it's fetched once via
    `projsync --file us_noaa_cshpgn.tif`. Skip rather than fail if a host
    hasn't fetched it, same spirit as the HAS_CS2CS skip above."""
    import subprocess

    try:
        result = subprocess.run(
            ["cct", *coords.NAD83_TO_WGS84_SOCAL_PIPELINE],
            input="32.71225 -117.16857 0 0",
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


HAS_CSHPGN_GRID = shutil.which("cct") is not None and _grid_available()


# The same downtown-San-Diego control point used for the State Plane
# transform above, this time expressed in its NAD83 geographic (lat, lon
# degrees) form -- close enough to the State Plane landmark table that a
# gross axis-order bug (feeding lon,lat instead of lat,lon into the
# leading `axisswap`) would move it by a large, obvious amount, not a
# fraction of a degree.
NAD83_KNOWN_POINT = ("611 W G St, San Diego (downtown), NAD83", (32.71225, -117.16857))


@unittest.skipUnless(HAS_CSHPGN_GRID, "cct or the us_noaa_cshpgn.tif NADCON grid is not available on this host")
class Nad83TransformTests(unittest.TestCase):
    def test_known_point_transforms_to_a_plausible_nearby_location(self):
        label, (lat_nad83, lon_nad83) = NAD83_KNOWN_POINT
        lat, lon = coords.batch_nad83_geographic_to_wgs84([(lat_nad83, lon_nad83)])[0]
        # NAD83/WGS84 agree to within about a meter in California -- this
        # is not the ~0.001 degree tolerance used for the State Plane
        # landmarks above (that budget exists to catch a wrong zone/axis,
        # not to bound a sub-meter datum shift), just confirmation the
        # result stayed extremely close to its input, not merely a proof
        # that some fixed offset was applied.
        self.assertAlmostEqual(lat, lat_nad83, delta=0.0001)
        self.assertAlmostEqual(lon, lon_nad83, delta=0.0001)
        self.assertTrue(coords.is_plausible_san_diego_point(lat, lon))

    def test_grid_based_transform_is_not_the_ballpark_identity(self):
        # The whole point of using cct + the explicit grid pipeline
        # instead of `cs2cs EPSG:4269 EPSG:4326` is that the latter's
        # default operation is a zero-shift no-op (see coords.py's top
        # docstring). Confirm the grid-based result is *not* bit-identical
        # to the untransformed input -- if this ever starts failing, the
        # pipeline has silently degraded back into an identity transform.
        _label, (lat_nad83, lon_nad83) = NAD83_KNOWN_POINT
        lat, lon = coords.batch_nad83_geographic_to_wgs84([(lat_nad83, lon_nad83)])[0]
        self.assertNotEqual((lat, lon), (lat_nad83, lon_nad83))

    def test_empty_input_returns_empty_output(self):
        self.assertEqual(coords.batch_nad83_geographic_to_wgs84([]), [])

    def test_batch_preserves_order_and_count(self):
        _label, point = NAD83_KNOWN_POINT
        result = coords.batch_nad83_geographic_to_wgs84([point, point])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], result[1])

    def test_missing_grid_raises_instead_of_silently_using_the_ballpark_transform(self):
        import subprocess

        bogus_pipeline = [
            arg.replace("us_noaa_cshpgn.tif", "us_noaa_cshpgn_DOES_NOT_EXIST.tif")
            for arg in coords.NAD83_TO_WGS84_SOCAL_PIPELINE
        ]
        with unittest.mock.patch.object(coords, "NAD83_TO_WGS84_SOCAL_PIPELINE", bogus_pipeline):
            with self.assertRaises(subprocess.CalledProcessError):
                coords.batch_nad83_geographic_to_wgs84([(32.71225, -117.16857)])


if __name__ == "__main__":
    unittest.main()
