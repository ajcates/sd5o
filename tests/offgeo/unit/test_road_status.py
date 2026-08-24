"""Unit tests for tools/offgeo/lib/road_status.py (OFF-101, R1 Group A)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools" / "offgeo"))

from lib import road_status  # noqa: E402


class ClassifySegmentTests(unittest.TestCase):
    def test_ordinary_constructed_dedicated_road(self):
        result = road_status.classify_segment(segstat="C", dedstat="D", pending="N", funclass="L")
        self.assertEqual(result.confidence, road_status.ORDINARY)

    def test_ordinary_maintained_dedicated_road(self):
        result = road_status.classify_segment(segstat="M", dedstat="D", pending="N", funclass="6")
        self.assertEqual(result.confidence, road_status.ORDINARY)

    def test_abandoned_is_excluded(self):
        result = road_status.classify_segment(segstat="M", dedstat="A", pending="N", funclass="L")
        self.assertEqual(result.confidence, road_status.EXCLUDED)

    def test_private_street_dedstat_is_fallback_not_excluded(self):
        # Private streets plausibly carry real mailing addresses -- spec.md
        # says fallback, not automatic exclusion.
        result = road_status.classify_segment(segstat="M", dedstat="P", pending="N", funclass="L")
        self.assertEqual(result.confidence, road_status.FALLBACK)
        self.assertTrue(any("Private street" in r for r in result.reasons))

    def test_private_street_funclass_is_also_fallback(self):
        result = road_status.classify_segment(segstat="M", dedstat="D", pending="N", funclass="7")
        self.assertEqual(result.confidence, road_status.FALLBACK)

    def test_undedicated_military_road_is_fallback(self):
        result = road_status.classify_segment(segstat="M", dedstat="U", pending="N", funclass="M")
        self.assertEqual(result.confidence, road_status.FALLBACK)

    def test_pending_recording_is_fallback(self):
        result = road_status.classify_segment(segstat="C", dedstat="D", pending="Y", funclass="L")
        self.assertEqual(result.confidence, road_status.FALLBACK)

    def test_approved_not_yet_constructed_is_fallback(self):
        result = road_status.classify_segment(segstat="A", dedstat="D", pending="N", funclass="L")
        self.assertEqual(result.confidence, road_status.FALLBACK)

    def test_tentative_is_fallback(self):
        result = road_status.classify_segment(segstat="T", dedstat="D", pending="N", funclass="L")
        self.assertEqual(result.confidence, road_status.FALLBACK)

    def test_blank_segstat_is_fallback_not_ordinary(self):
        result = road_status.classify_segment(segstat="", dedstat="D", pending="N", funclass="L")
        self.assertEqual(result.confidence, road_status.FALLBACK)

    def test_blank_dedstat_is_fallback_not_ordinary(self):
        result = road_status.classify_segment(segstat="C", dedstat="", pending="N", funclass="L")
        self.assertEqual(result.confidence, road_status.FALLBACK)

    def test_reasons_are_never_empty_for_fallback_or_excluded(self):
        for segstat, dedstat, pending, funclass in [
            ("A", "A", "Y", "7"),
            ("T", "P", "N", "P"),
        ]:
            result = road_status.classify_segment(segstat, dedstat, pending, funclass)
            self.assertNotEqual(result.confidence, road_status.ORDINARY)
            self.assertTrue(result.reasons)


if __name__ == "__main__":
    unittest.main()
