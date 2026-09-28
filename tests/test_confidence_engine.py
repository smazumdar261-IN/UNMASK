"""Unit tests for the Confidence System (Phase 5)."""

import json
import unittest

from core.confidence import (
    Confidence,
    ConfidenceEngine,
    ConfidenceLevel,
    TransformationCategory,
)
from core.provenance import ProvenanceRecord, ProvenanceTracker, SourceLocation


class TestConfidenceEngine(unittest.TestCase):
    """Test suite for ConfidenceLevel, TransformationCategory, and ConfidenceEngine."""

    def test_confidence_level_ordering(self) -> None:
        self.assertGreater(ConfidenceLevel.CERTAIN, ConfidenceLevel.HIGH)
        self.assertGreater(ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        self.assertGreater(ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW)
        self.assertGreater(ConfidenceLevel.LOW, ConfidenceLevel.UNKNOWN)

        self.assertTrue(ConfidenceLevel.CERTAIN >= ConfidenceLevel.HIGH)
        self.assertTrue(ConfidenceLevel.HIGH >= ConfidenceLevel.HIGH)
        self.assertFalse(ConfidenceLevel.LOW >= ConfidenceLevel.HIGH)
        self.assertFalse(ConfidenceLevel.MEDIUM > ConfidenceLevel.CERTAIN)

    def test_from_str_parsing(self) -> None:
        self.assertEqual(ConfidenceLevel.from_str("certain"), ConfidenceLevel.CERTAIN)
        self.assertEqual(ConfidenceLevel.from_str("HIGH"), ConfidenceLevel.HIGH)
        self.assertEqual(ConfidenceLevel.from_str("  medium  "), ConfidenceLevel.MEDIUM)
        self.assertEqual(ConfidenceLevel.from_str("low"), ConfidenceLevel.LOW)
        self.assertEqual(ConfidenceLevel.from_str("unknown"), ConfidenceLevel.UNKNOWN)

        with self.assertRaises(ValueError):
            ConfidenceLevel.from_str("invalid_level")

    def test_transformation_categories(self) -> None:
        expected = {"Recovered", "Inferred", "Simplified", "Unresolved"}
        actual = {cat.value for cat in TransformationCategory}
        self.assertEqual(expected, actual)

    def test_confidence_factories_and_scores(self) -> None:
        c_cert = Confidence.certain("reason")
        self.assertEqual(c_cert.level, ConfidenceLevel.CERTAIN)
        self.assertEqual(c_cert.score, 1.0)
        self.assertEqual(c_cert.category, TransformationCategory.SIMPLIFIED)

        c_high = Confidence.high("reason", TransformationCategory.RECOVERED)
        self.assertEqual(c_high.level, ConfidenceLevel.HIGH)
        self.assertEqual(c_high.score, 0.85)
        self.assertEqual(c_high.category, TransformationCategory.RECOVERED)

        c_med = Confidence.medium("reason")
        self.assertEqual(c_med.level, ConfidenceLevel.MEDIUM)
        self.assertEqual(c_med.score, 0.50)

        c_low = Confidence.low("reason")
        self.assertEqual(c_low.level, ConfidenceLevel.LOW)
        self.assertEqual(c_low.score, 0.25)

        c_unk = Confidence.unknown("reason")
        self.assertEqual(c_unk.level, ConfidenceLevel.UNKNOWN)
        self.assertEqual(c_unk.score, 0.0)
        self.assertEqual(c_unk.category, TransformationCategory.UNRESOLVED)

    def test_confidence_engine_metrics_and_filtering(self) -> None:
        tracker = ProvenanceTracker()
        tracker.record("PassA", "orig1", "trans1", Confidence.certain("p1", TransformationCategory.RECOVERED))
        tracker.record("PassB", "orig2", "trans2", Confidence.high("p2", TransformationCategory.SIMPLIFIED))
        tracker.record("PassC", "orig3", "trans3", Confidence.medium("p3", TransformationCategory.INFERRED))
        tracker.record_unresolved("PassD", "orig4", "Cannot evaluate dynamic call")

        engine = tracker.get_engine()
        self.assertEqual(engine.total_count, 4)

        # Average: (1.0 + 0.85 + 0.50 + 0.0) / 4 = 2.35 / 4 = 0.5875
        self.assertEqual(engine.compute_average_confidence(), 0.5875)

        # Level breakdown
        self.assertEqual(engine.level_breakdown["CERTAIN"], 1)
        self.assertEqual(engine.level_breakdown["HIGH"], 1)
        self.assertEqual(engine.level_breakdown["MEDIUM"], 1)
        self.assertEqual(engine.level_breakdown["UNKNOWN"], 1)
        self.assertEqual(engine.level_breakdown["LOW"], 0)

        # Category breakdown
        self.assertEqual(engine.category_breakdown["Recovered"], 1)
        self.assertEqual(engine.category_breakdown["Simplified"], 1)
        self.assertEqual(engine.category_breakdown["Inferred"], 1)
        self.assertEqual(engine.category_breakdown["Unresolved"], 1)

        # Filtering by min confidence
        high_records = engine.filter_by_min_confidence(ConfidenceLevel.HIGH)
        self.assertEqual(len(high_records), 2)  # CERTAIN and HIGH

    def test_report_formatting(self) -> None:
        tracker = ProvenanceTracker()
        loc = SourceLocation(filename="test.py", start_line=10, start_col=5)
        tracker.record("Pass1", "x = 1+1", "x = 2", Confidence.certain("folded"), loc)
        tracker.record_unresolved("Pass2", "eval(input)", "Dynamic code execution", loc)

        # Text format
        text_report = tracker.format_report("text")
        self.assertIn("Universal Deobfuscator Audit Report", text_report)
        self.assertIn("[CERTAIN]", text_report)
        self.assertIn("Unresolved: 1", text_report)

        # JSON format
        json_report = tracker.format_report("json")
        data = json.loads(json_report)
        self.assertEqual(data["total_transformations"], 2)
        self.assertEqual(data["category_breakdown"]["Unresolved"], 1)
        self.assertEqual(len(data["records"]), 2)
        self.assertEqual(data["records"][0]["pass_name"], "Pass1")

        # Markdown format
        md_report = tracker.format_report("markdown")
        self.assertIn("# Universal Deobfuscator Audit Report", md_report)
        self.assertIn("| Step | Pass | Level |", md_report)
        self.assertIn("`CERTAIN`", md_report)


if __name__ == "__main__":
    unittest.main()
