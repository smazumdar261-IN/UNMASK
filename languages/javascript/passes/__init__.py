"""JavaScript deobfuscation passes."""

from languages.javascript.passes.constant_propagation import JSConstantPropagationPass
from languages.javascript.passes.expression_folding import JSExpressionFoldingPass
from languages.javascript.passes.decoders import JSDecoderDetectionPass
from languages.javascript.passes.string_reconstruction import JSStringReconstructionPass
from languages.javascript.passes.property_normalization import JSPropertyNormalizationPass
from languages.javascript.passes.iife_normalization import JSIIFENormalizationPass

__all__ = [
    "JSConstantPropagationPass",
    "JSExpressionFoldingPass",
    "JSDecoderDetectionPass",
    "JSStringReconstructionPass",
    "JSPropertyNormalizationPass",
    "JSIIFENormalizationPass",
]
