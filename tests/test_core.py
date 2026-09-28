"""Unit tests for core architecture (Phase 0)."""

import unittest

from core.confidence import Confidence, ConfidenceLevel, TransformationCategory
from core.ir import IRConstant, IRFunction, IRModule, IRVariable
from core.pipeline import Pass, Pipeline
from core.provenance import ProvenanceTracker, SourceLocation


class MockPass(Pass):
    """Test transformation pass."""

    name = "MockPass"
    description = "Mock pass for pipeline verification"

    def run(self, target: str, tracker: ProvenanceTracker) -> str:
        tracker.record(
            pass_name=self.name,
            original=target,
            transformed="transformed_output",
            confidence=Confidence.certain("Mock transformation applied"),
            location=SourceLocation("test.py", 1, 0, 1, 10),
        )
        return "transformed_output"


class TestCore(unittest.TestCase):
    """Test suite for core pipeline, provenance, and IR."""

    def test_confidence_factories(self) -> None:
        c_certain = Confidence.certain("Syntax verified")
        self.assertEqual(c_certain.level, ConfidenceLevel.CERTAIN)
        self.assertEqual(c_certain.score, 1.0)

        c_unknown = Confidence.unknown("Dynamic evaluation required")
        self.assertEqual(c_unknown.level, ConfidenceLevel.UNKNOWN)
        self.assertEqual(c_unknown.category, TransformationCategory.UNRESOLVED)

    def test_provenance_tracker(self) -> None:
        tracker = ProvenanceTracker()
        rec = tracker.record(
            pass_name="ConstFold",
            original="1 + 2",
            transformed="3",
            confidence=Confidence.certain("Integer addition"),
            location=SourceLocation("app.py", 5, 4, 5, 9),
        )
        self.assertEqual(rec.step_id, 1)
        self.assertEqual(tracker.count_by_level(ConfidenceLevel.CERTAIN), 1)
        self.assertIn("[CERTAIN] ConstFold at app.py:L5:4-L5:9", rec.summary())

    def test_pipeline_execution(self) -> None:
        pipeline = Pipeline()
        pipeline.add_pass(MockPass())
        output = pipeline.execute("initial_input")

        self.assertEqual(output, "transformed_output")
        self.assertEqual(len(pipeline.tracker.records), 1)

        report = pipeline.generate_report()
        self.assertIn("Total transformations applied: 1", report)
        self.assertIn("[CERTAIN]: 1", report)

    def test_ir_nodes(self) -> None:
        const = IRConstant(value=42)
        self.assertEqual(const.type_name, "int")

        var = IRVariable(name="counter")
        self.assertEqual(var.name, "counter")

        func = IRFunction(name="calculate", parameters=["a", "b"])
        self.assertEqual(func.name, "calculate")
        self.assertEqual(len(func.parameters), 2)

        mod = IRModule(name="test_mod", language="python", body=[func])
        self.assertEqual(mod.language, "python")
        self.assertEqual(len(mod.body), 1)


if __name__ == "__main__":
    unittest.main()
