"""Unit tests for tools/offgeo/lib/normalize.py (OFF-102, R1 Group A).

Two layers: targeted unit tests for each function, and a corpus-wide
robustness/behavior check against every one of the 50 real addresses in
tests/offgeo/fixtures/addresses.json (OFF-008's rolling corpus) -- not a
hand-picked subset. That corpus's own `categories` field (ordinary_numbered,
has_directional, slash_intersection_unspaced, highway) is real ground
truth already captured from the live feed, so this test checks the
normalizer's behavior against it rather than re-inventing expectations.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import normalize  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_PATH = REPO_ROOT / "tests/offgeo/fixtures/addresses.json"


class TextNormalizationTests(unittest.TestCase):
    def test_uppercases_trims_and_collapses_whitespace(self):
        self.assertEqual(normalize.normalize_text("  100  n el camino real "), "100 N EL CAMINO REAL")

    def test_strips_periods(self):
        self.assertEqual(normalize.normalize_text("100 N. Main St."), "100 N MAIN ST")

    def test_preserves_intersection_and_fraction_punctuation(self):
        self.assertEqual(normalize.normalize_text("main st/2nd ave"), "MAIN ST/2ND AVE")
        self.assertEqual(normalize.normalize_text("123 1/2 main st"), "123 1/2 MAIN ST")


class UnitStrippingTests(unittest.TestCase):
    def test_strips_trailing_apartment(self):
        self.assertEqual(normalize.strip_unit_designator("123 MAIN ST APT 4"), "123 MAIN ST")

    def test_strips_trailing_unit_letter(self):
        self.assertEqual(normalize.strip_unit_designator("123 MAIN ST UNIT B"), "123 MAIN ST")

    def test_strips_hash_unit(self):
        self.assertEqual(normalize.strip_unit_designator("123 MAIN ST #12"), "123 MAIN ST")

    def test_leaves_addresses_without_a_unit_untouched(self):
        self.assertEqual(normalize.strip_unit_designator("123 MAIN ST"), "123 MAIN ST")


class DirectionSuffixCanonicalizationTests(unittest.TestCase):
    def test_direction_abbreviation_and_word_collapse_together(self):
        self.assertEqual(normalize.canonicalize_direction("N"), "N")
        self.assertEqual(normalize.canonicalize_direction("NORTH"), "N")

    def test_unknown_direction_returns_none(self):
        self.assertIsNone(normalize.canonicalize_direction("UP"))

    def test_travel_direction_marker_is_not_a_street_direction(self):
        # NB ("northbound") must NOT collapse into N -- see normalize.py's
        # TRAVEL_DIRECTION_MARKERS comment for why these are kept distinct.
        self.assertIsNone(normalize.canonicalize_direction("NB"))
        self.assertIn("NB", normalize.TRAVEL_DIRECTION_MARKERS)

    def test_suffix_abbreviations_from_both_sangis_tables_collapse_together(self):
        # "BL" (RD20SFX, 2-letter) and "BLVD" (RD30SFX, 4-letter) and
        # "BOULEVARD" (long form) are three real spellings of one concept.
        self.assertEqual(normalize.canonicalize_suffix("BL"), "BOULEVARD")
        self.assertEqual(normalize.canonicalize_suffix("BLVD"), "BOULEVARD")
        self.assertEqual(normalize.canonicalize_suffix("BOULEVARD"), "BOULEVARD")

    def test_unknown_suffix_returns_none(self):
        self.assertIsNone(normalize.canonicalize_suffix("REAL"))  # "El Camino Real"


class BlockNotationTests(unittest.TestCase):
    def test_recognizes_block_of_form(self):
        result = normalize.parse_block_notation("1200 BLOCK OF MAIN ST")
        self.assertEqual(result, (1200, "MAIN ST"))

    def test_recognizes_block_without_of(self):
        result = normalize.parse_block_notation("1200 BLOCK MAIN ST")
        self.assertEqual(result, (1200, "MAIN ST"))

    def test_non_block_text_returns_none(self):
        self.assertIsNone(normalize.parse_block_notation("1200 MAIN ST"))


class IntersectionSplittingTests(unittest.TestCase):
    def test_splits_unspaced_slash(self):
        self.assertEqual(normalize.split_intersection("MAIN ST/2ND AVE"), ("MAIN ST", "2ND AVE"))

    def test_splits_spaced_ampersand(self):
        self.assertEqual(normalize.split_intersection("MAIN ST & 2ND AVE"), ("MAIN ST", "2ND AVE"))

    def test_splits_at_word(self):
        self.assertEqual(normalize.split_intersection("MAIN ST AT 2ND AVE"), ("MAIN ST", "2ND AVE"))

    def test_fraction_slash_is_not_treated_as_intersection(self):
        self.assertIsNone(normalize.split_intersection("123 1/2 MAIN ST"))

    def test_ordinary_address_is_not_an_intersection(self):
        self.assertIsNone(normalize.split_intersection("100 MAIN ST"))


class HighwayRouteTests(unittest.TestCase):
    def test_recognizes_highway_number(self):
        self.assertEqual(normalize.parse_highway_route("OLDE HIGHWAY 80"), 80)

    def test_recognizes_interstate_number(self):
        self.assertEqual(normalize.parse_highway_route("NB INTERSTATE 5"), 5)

    def test_recognizes_state_route_number(self):
        self.assertEqual(normalize.parse_highway_route("STATE ROUTE 76"), 76)

    def test_named_highway_without_a_number_is_not_a_route(self):
        # "Old Julian Hwy" is a named road, not a numbered route -- HWY
        # here is an ordinary suffix, handled by parse_street_name instead.
        self.assertIsNone(normalize.parse_highway_route("OLD JULIAN HWY"))


class StreetNameParsingTests(unittest.TestCase):
    def test_plain_street_with_suffix(self):
        s = normalize.parse_street_name("MAST BL")
        self.assertEqual(s.name, "MAST")
        self.assertEqual(s.suffix, "BOULEVARD")
        self.assertIsNone(s.pdir)

    def test_leading_direction_is_extracted(self):
        s = normalize.parse_street_name("N EL CAMINO REAL")
        self.assertEqual(s.pdir, "N")
        self.assertEqual(s.name, "EL CAMINO REAL")
        self.assertIsNone(s.suffix)  # "REAL" is not a recognized suffix

    def test_unrecognized_trailing_word_stays_in_the_name(self):
        s = normalize.parse_street_name("VIA TERRASSA")
        self.assertEqual(s.name, "VIA TERRASSA")
        self.assertIsNone(s.suffix)

    def test_highway_number_short_circuits_suffix_parsing(self):
        s = normalize.parse_street_name("OLDE HIGHWAY 80")
        self.assertTrue(s.is_highway)
        self.assertEqual(s.route_number, 80)

    def test_canonical_key_joins_present_components(self):
        s = normalize.parse_street_name("N MAST BL")
        self.assertEqual(s.canonical_key(), "N MAST BOULEVARD")


class ParseAddressCorpusTests(unittest.TestCase):
    """Behavior against every real address in the OFF-008 fixture corpus."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = json.loads(FIXTURES_PATH.read_text())["fixtures"]

    def test_every_real_address_parses_without_raising(self):
        for fixture in self.fixtures:
            with self.subTest(address=fixture["address"]):
                normalize.parse_address(fixture["address"])  # must not raise

    def test_ordinary_numbered_addresses_get_a_house_number(self):
        for fixture in self.fixtures:
            if "ordinary_numbered" not in fixture["categories"]:
                continue
            with self.subTest(address=fixture["address"]):
                parsed = normalize.parse_address(fixture["address"])
                self.assertIsNotNone(parsed.house_number, f"expected a house number for {fixture['address']!r}")
                self.assertFalse(parsed.is_intersection)

    def test_slash_intersections_are_recognized_and_split_in_two(self):
        for fixture in self.fixtures:
            if "slash_intersection_unspaced" not in fixture["categories"]:
                continue
            with self.subTest(address=fixture["address"]):
                parsed = normalize.parse_address(fixture["address"])
                self.assertTrue(parsed.is_intersection, f"expected an intersection for {fixture['address']!r}")
                self.assertEqual(len(parsed.streets), 2)
                self.assertIsNone(parsed.house_number)

    def test_has_directional_addresses_get_a_pdir_on_at_least_one_street(self):
        for fixture in self.fixtures:
            if "has_directional" not in fixture["categories"]:
                continue
            with self.subTest(address=fixture["address"]):
                parsed = normalize.parse_address(fixture["address"])
                self.assertTrue(
                    any(s.pdir is not None for s in parsed.streets),
                    f"expected a recognized direction somewhere in {fixture['address']!r}",
                )

    def test_highway_addresses_are_flagged_as_highway_or_carry_a_highway_suffix(self):
        for fixture in self.fixtures:
            if "highway" not in fixture["categories"]:
                continue
            with self.subTest(address=fixture["address"]):
                parsed = normalize.parse_address(fixture["address"])
                self.assertTrue(
                    any(s.is_highway or s.suffix == "HIGHWAY" for s in parsed.streets),
                    f"expected a highway signal somewhere in {fixture['address']!r}",
                )


if __name__ == "__main__":
    unittest.main()
