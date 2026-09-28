"""Common Intermediate Representation Pipeline execution engine.

Per Section 16 & Phase 10:
Orchestrates transformation passes, CFG construction, and validation on Common IR trees.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.confidence import ConfidenceLevel
from core.ir import IRModule, IRValidator, format_ir
from core.ir_cfg import IRCFG
from core.ir_passes import (
    IRConstantPropagation,
    IRDeadCodeElimination,
    IRDecoderEvaluation,
    IRExpressionFolding,
    IRStringReconstruction,
)
from core.pipeline import Pass, Pipeline
from core.provenance import ProvenanceTracker

logger = logging.getLogger("universal_deobfuscator.ir_pipeline")


class IRPipeline:
    """Specialized execution pipeline for Common IR optimization and analysis."""

    def __init__(
        self,
        passes: Optional[List[Pass]] = None,
        tracker: Optional[ProvenanceTracker] = None,
        min_confidence: ConfidenceLevel = ConfidenceLevel.LOW,
    ) -> None:
        self.tracker: ProvenanceTracker = tracker or ProvenanceTracker(min_confidence=min_confidence)
        self.passes: List[Pass] = passes or self.default_passes()

    @classmethod
    def default_passes(cls) -> List[Pass]:
        """Default suite of universal deobfuscation passes."""
        return [
            IRDecoderEvaluation(),
            IRStringReconstruction(),
            IRConstantPropagation(),
            IRExpressionFolding(),
            IRDeadCodeElimination(),
        ]

    def add_pass(self, p: Pass) -> "IRPipeline":
        self.passes.append(p)
        return self

    def execute(
        self,
        ir_module: IRModule,
        max_iterations: int = 5,
        until_convergence: bool = True,
    ) -> IRModule:
        """Run all registered passes sequentially on an IRModule."""
        pipeline = Pipeline(passes=self.passes, tracker=self.tracker)
        return pipeline.execute(ir_module, max_iterations=max_iterations, until_convergence=until_convergence)

    def build_cfgs(self, ir_module: IRModule) -> Dict[str, IRCFG]:
        """Construct CFGs for the module and all contained functions."""
        return IRCFG.build_from_module(ir_module)

    def validate(self, ir_module: IRModule) -> List[str]:
        """Validate structural integrity of the IR module."""
        return IRValidator.validate(ir_module)

    def dump(self, ir_module: IRModule) -> str:
        """Generate human-readable textual representation of the IR module."""
        return format_ir(ir_module)

    def generate_report(self, format_type: str = "text") -> str:
        """Generate provenance audit report."""
        return self.tracker.format_report(format_type)
