"""Deobfuscation passes."""

from passes.expression_folding import ExpressionFoldingPass
from passes.constant_propagation import ConstantPropagationPass
from passes.string_reconstruction import StringReconstructionPass
from passes.decoder_detection import DecoderDetectionPass
from passes.dead_code import DeadCodeEliminationPass
from passes.function_inlining import FunctionInliningPass
from passes.import_analysis import ImportNormalizationPass
from passes.simplify import SimplificationPass
from passes.cfg_reduction import CFGReductionPass
from passes.cff_recovery import ControlFlowFlatteningPass
from passes.symbolic_evaluation import SymbolicEvaluationPass
from passes.type_annotation import TypeAnnotationPass

__all__ = [
    "ExpressionFoldingPass",
    "ConstantPropagationPass",
    "StringReconstructionPass",
    "DecoderDetectionPass",
    "DeadCodeEliminationPass",
    "FunctionInliningPass",
    "ImportNormalizationPass",
    "SimplificationPass",
    "CFGReductionPass",
    "ControlFlowFlatteningPass",
    "SymbolicEvaluationPass",
    "TypeAnnotationPass",
]
