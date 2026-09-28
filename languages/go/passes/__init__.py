"""Go deobfuscation passes.

Per Section 15 of the Master Specification (Phase 9: Go):
Exports passes for:
- Constant propagation
- Expression folding
- String reconstruction
- Decoder detection (base64, hex, strconv, strings)
- Dead code elimination
"""

from languages.go.passes.constant_propagation import GoConstantPropagationPass
from languages.go.passes.dead_code import GoDeadCodePass
from languages.go.passes.decoders import GoDecoderDetectionPass
from languages.go.passes.expression_folding import GoExpressionFoldingPass
from languages.go.passes.string_reconstruction import GoStringReconstructionPass

__all__ = [
    "GoConstantPropagationPass",
    "GoExpressionFoldingPass",
    "GoStringReconstructionPass",
    "GoDecoderDetectionPass",
    "GoDeadCodePass",
]
