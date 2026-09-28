"""Program analysis package for Universal Deobfuscator."""

from analysis.dataflow import (
    DataFlowAnalyzer,
    Definition,
    VariableUse,
    is_pure_expression,
)
from analysis.callgraph import CallGraphAnalyzer, FunctionSignature
from analysis.imports import ImportAnalyzer, ResolvedTarget
from analysis.cfg import BasicBlock, CFGEdge, CFGBuilder, ControlFlowGraph, EdgeType
from analysis.symbolic import (
    SymbolicValue,
    SymbolicConstant,
    SymbolicVariable,
    SymbolicBinaryOp,
    SymbolicUnaryOp,
    SymbolicEvaluator,
)
from analysis.reaching_definitions import ReachingDefinitionsAnalyzer, DependencyGraph
from analysis.type_inference import TypeInferenceEngine

__all__ = [
    "DataFlowAnalyzer",
    "Definition",
    "VariableUse",
    "is_pure_expression",
    "CallGraphAnalyzer",
    "FunctionSignature",
    "ImportAnalyzer",
    "ResolvedTarget",
    "BasicBlock",
    "CFGEdge",
    "CFGBuilder",
    "ControlFlowGraph",
    "EdgeType",
    "SymbolicValue",
    "SymbolicConstant",
    "SymbolicVariable",
    "SymbolicBinaryOp",
    "SymbolicUnaryOp",
    "SymbolicEvaluator",
    "ReachingDefinitionsAnalyzer",
    "DependencyGraph",
    "TypeInferenceEngine",
]
