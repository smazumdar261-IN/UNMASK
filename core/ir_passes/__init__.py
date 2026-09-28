"""Common IR optimization and deobfuscation passes.

Per Section 16 & Phase 10:
Provides universal passes operating directly on Common IR:
- Constant Propagation
- Expression Folding
- Dead Code Elimination
- String Reconstruction
- Decoder Evaluation
"""

from __future__ import annotations

from typing import Optional

from core.ir import IRModule
from core.ir_passes.constant_propagation import IRConstantPropagation
from core.ir_passes.dead_code import IRDeadCodeElimination
from core.ir_passes.decoders import IRDecoderEvaluation
from core.ir_passes.expression_folding import IRExpressionFolding
from core.ir_passes.string_reconstruction import IRStringReconstruction
from core.pipeline import Pipeline
from core.provenance import ProvenanceTracker

__all__ = [
    "IRConstantPropagation",
    "IRExpressionFolding",
    "IRDeadCodeElimination",
    "IRStringReconstruction",
    "IRDecoderEvaluation",
    "optimize_ir",
]


def optimize_ir(
    ir_module: IRModule,
    tracker: Optional[ProvenanceTracker] = None,
    max_iterations: int = 5,
) -> IRModule:
    """Run all universal IR passes sequentially until convergence or max_iterations."""
    pipeline = Pipeline(
        passes=[
            IRDecoderEvaluation(),
            IRStringReconstruction(),
            IRConstantPropagation(),
            IRExpressionFolding(),
            IRDeadCodeElimination(),
        ],
        tracker=tracker or ProvenanceTracker(),
    )
    return pipeline.execute(ir_module, max_iterations=max_iterations, until_convergence=True)
