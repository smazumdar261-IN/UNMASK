"""Java deobfuscation passes.

Per Section 14 of the Master Specification (Phase 8: Java):
Exports passes for Java constant propagation, expression folding,
decoder detection, string reconstruction, and dead code elimination.
"""

from languages.java.passes.constant_propagation import JavaConstantPropagationPass
from languages.java.passes.decoders import JavaDecoderDetectionPass
from languages.java.passes.expression_folding import JavaExpressionFoldingPass
from languages.java.passes.string_reconstruction import JavaStringReconstructionPass
from languages.java.passes.dead_code import JavaDeadCodePass

__all__ = [
    "JavaConstantPropagationPass",
    "JavaExpressionFoldingPass",
    "JavaDecoderDetectionPass",
    "JavaStringReconstructionPass",
    "JavaDeadCodePass",
]
