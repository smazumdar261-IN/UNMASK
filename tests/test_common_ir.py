"""Comprehensive tests for Common Intermediate Representation (IR) refinement (Phase 10).

Per Section 16 & Phase 10 of the Master Specification:
- All Section 16 IR constructs (Module, Function, Variable, Constant, Expression,
  Call, Assignment, Branch, Loop, Return, Exception, Import, String, BinaryOperation, UnaryOperation)
- Universal Visitor and Transformer patterns
- IR Pretty Printer and Validator
- Bidirectional converters for Python, JavaScript, TypeScript, Java, and Go
- Cross-language CFG analysis on IR (Dominators, Reachability, Natural Loops, ASCII dump)
- Universal IR deobfuscation passes (Constant propagation, Expression folding,
  Dead code elimination, String reconstruction, Decoder evaluation)
- IRPipeline multi-pass execution and provenance tracking
- CLI integration (ir subcommand and --use-ir flag)
"""

import io
import unittest
from unittest.mock import patch

from core.confidence import ConfidenceLevel
from core.ir import (
    IRAssignment,
    IRBinaryOperation,
    IRBlock,
    IRBranch,
    IRBreak,
    IRCall,
    IRConstant,
    IRContinue,
    IRDictLiteral,
    IRExceptionHandler,
    IRExpressionStatement,
    IRFunction,
    IRImport,
    IRIndexAccess,
    IRListLiteral,
    IRLoop,
    IRMemberAccess,
    IRModule,
    IRPass,
    IRPrinter,
    IRRaise,
    IRReturn,
    IRString,
    IRTransformer,
    IRTryExcept,
    IRUnaryOperation,
    IRValidator,
    IRVariable,
    IRVisitor,
    format_ir,
)
from core.ir_cfg import IRBasicBlock, IRCFG, IRCFGEdge, IREdgeType
from core.ir_passes import (
    IRConstantPropagation,
    IRDeadCodeElimination,
    IRDecoderEvaluation,
    IRExpressionFolding,
    IRStringReconstruction,
    optimize_ir,
)
from core.ir_pipeline import IRPipeline
from core.provenance import ProvenanceTracker
from languages import registry
import languages.go
import languages.java
import languages.javascript
import languages.python
import languages.typescript
from languages.go.ir_converter import GoIRConverter
from languages.java.ir_converter import JavaIRConverter
from languages.javascript.ir_converter import JSIRConverter
from languages.python.ir_converter import PythonIRConverter
from languages.typescript.ir_converter import TSIRConverter
import main


class TestCommonIRNodes(unittest.TestCase):
    """Verifies all Section 16 Common IR node definitions, attributes, and helpers."""

    def test_all_section_16_nodes_instantiation(self) -> None:
        const = IRConstant(value=100)
        self.assertEqual(const.type_name, "int")

        string_node = IRString(value="test_str")
        self.assertEqual(string_node.type_name, "str")
        self.assertIsInstance(string_node, IRConstant)

        var = IRVariable(name="counter")
        self.assertEqual(var.name, "counter")

        bin_op = IRBinaryOperation(op="+", left=var, right=const)
        self.assertEqual(bin_op.op, "+")

        un_op = IRUnaryOperation(op="-", operand=var)
        self.assertEqual(un_op.op, "-")

        call = IRCall(callee=var, args=[const])
        self.assertEqual(len(call.args), 1)

        mem = IRMemberAccess(target=var, member="length")
        self.assertEqual(mem.member, "length")

        idx = IRIndexAccess(target=var, index=const)
        self.assertEqual(idx.index, const)

        list_lit = IRListLiteral(elements=[const, string_node])
        self.assertEqual(len(list_lit.elements), 2)

        dict_lit = IRDictLiteral(keys=[string_node], values=[const])
        self.assertEqual(len(dict_lit.keys), 1)

        assign = IRAssignment(target=var, value=bin_op)
        self.assertEqual(assign.target, var)

        expr_stmt = IRExpressionStatement(expression=call)
        self.assertEqual(expr_stmt.expression, call)

        branch = IRBranch(condition=const, body=[assign], orelse=[])
        self.assertEqual(len(branch.body), 1)

        loop = IRLoop(condition=const, body=[assign])
        self.assertFalse(loop.is_for)

        ret = IRReturn(value=const)
        self.assertEqual(ret.value, const)

        brk = IRBreak()
        self.assertIsNone(brk.label)

        cont = IRContinue()
        self.assertIsNone(cont.label)

        noop = IRPass()
        self.assertIsNotNone(noop)

        raise_stmt = IRRaise(exception=string_node)
        self.assertEqual(raise_stmt.exception, string_node)

        handler = IRExceptionHandler(exception_type="Exception", variable_name="e", body=[assign])
        try_except = IRTryExcept(body=[assign], handlers=[handler], orelse=[], finalbody=[])
        self.assertEqual(len(try_except.handlers), 1)

        block = IRBlock(statements=[assign, ret])
        self.assertEqual(len(block.statements), 2)

        imp = IRImport(module_name="os", alias="my_os", imported_names={"path": None})
        self.assertEqual(imp.module_name, "os")

        fn = IRFunction(name="compute", parameters=["x", "y"], body=[assign, ret], return_type="int")
        self.assertEqual(fn.name, "compute")
        self.assertEqual(fn.return_type, "int")

        mod = IRModule(name="test_mod", language="test_lang", body=[imp, fn])
        self.assertEqual(mod.language, "test_lang")
        self.assertEqual(len(mod.body), 2)

    def test_ir_visitor_and_transformer(self) -> None:
        mod = IRModule(
            name="demo",
            body=[
                IRAssignment(target=IRVariable(name="a"), value=IRConstant(value=10)),
                IRAssignment(target=IRVariable(name="b"), value=IRConstant(value=20)),
            ],
        )

        visited_names = []

        class TestVisitor(IRVisitor):
            def visit_IRVariable(self, node: IRVariable) -> None:
                visited_names.append(node.name)

        TestVisitor().visit(mod)
        self.assertEqual(visited_names, ["a", "b"])

        class TestMultiplier(IRTransformer):
            def visit_IRConstant(self, node: IRConstant) -> IRConstant:
                if isinstance(node.value, int):
                    return IRConstant(value=node.value * 2)
                return node

        transformed_mod = TestMultiplier().visit(mod)
        self.assertEqual(transformed_mod.body[0].value.value, 20)
        self.assertEqual(transformed_mod.body[1].value.value, 40)

    def test_ir_printer_and_validator(self) -> None:
        fn = IRFunction(
            name="add",
            parameters=["a", "b"],
            body=[
                IRReturn(value=IRBinaryOperation(op="+", left=IRVariable(name="a"), right=IRVariable(name="b")))
            ],
            return_type="int",
        )
        mod = IRModule(name="math", language="universal", body=[fn])
        text = format_ir(mod)

        self.assertIn("module math (language=universal):", text)
        self.assertIn("def add(a, b) -> int:", text)
        self.assertIn("return (a + b)", text)

        # Validator tests
        self.assertEqual(IRValidator.validate(mod), [])

        bad_assign = IRAssignment(target=None, value=None)  # type: ignore
        issues = IRValidator.validate(bad_assign)
        self.assertTrue(len(issues) >= 2)


class TestIRBidirectionalConverters(unittest.TestCase):
    """Tests bidirectional AST <-> Common IR translation for Python, JS, TS, Java, and Go."""

    def test_python_ir_converter_bidirectional(self) -> None:
        py_code = """
def calculate(x):
    y = x + 10
    if y > 20:
        return y * 2
    return y
"""
        lang = registry.get("python")
        py_ast = lang.parse(py_code)
        ir_mod = PythonIRConverter.to_ir(py_ast)

        self.assertEqual(ir_mod.language, "python")
        self.assertEqual(len(ir_mod.body), 1)
        fn_ir = ir_mod.body[0]
        self.assertIsInstance(fn_ir, IRFunction)
        self.assertEqual(fn_ir.name, "calculate")
        self.assertEqual(fn_ir.parameters, ["x"])

        # Reverse back to Python AST
        recovered_ast = PythonIRConverter.from_ir(ir_mod)
        unparsed = lang.unparse(recovered_ast)
        self.assertIn("def calculate(x):", unparsed)
        self.assertIn("y = x + 10", unparsed)
        self.assertIn("if y > 20:", unparsed)

    def test_javascript_ir_converter_bidirectional(self) -> None:
        js_code = """
function processData(val) {
    var count = val + 5;
    if (count > 10) {
        return count;
    }
    return 0;
}
"""
        lang = registry.get("javascript")
        js_ast = lang.parse(js_code)
        ir_mod = JSIRConverter.to_ir(js_ast)

        self.assertEqual(ir_mod.language, "javascript")
        self.assertEqual(len(ir_mod.body), 1)
        fn_ir = ir_mod.body[0]
        self.assertIsInstance(fn_ir, IRFunction)
        self.assertEqual(fn_ir.name, "processData")

        # Reverse back to JS AST
        recovered_ast = JSIRConverter.from_ir(ir_mod)
        unparsed = lang.unparse(recovered_ast)
        self.assertIn("function processData(val)", unparsed)
        self.assertIn("var count = val + 5;", unparsed)

    def test_typescript_ir_converter_bidirectional(self) -> None:
        ts_code = """
function greet(user) {
    var msg = "Hello " + user;
    return msg;
}
"""
        lang = registry.get("typescript")
        ts_ast = lang.parse(ts_code)
        ir_mod = TSIRConverter.to_ir(ts_ast)

        self.assertEqual(ir_mod.language, "typescript")
        recovered_ast = TSIRConverter.from_ir(ir_mod)
        unparsed = lang.unparse(recovered_ast)
        self.assertIn("function greet(user)", unparsed)

    def test_java_ir_converter_bidirectional(self) -> None:
        java_code = """
package com.test;

public class Worker {
    public static int run(int val) {
        int x = val + 1;
        return x;
    }
}
"""
        lang = registry.get("java")
        java_ast = lang.parse(java_code)
        ir_mod = JavaIRConverter.to_ir(java_ast)

        self.assertEqual(ir_mod.language, "java")
        self.assertTrue(any(isinstance(s, IRFunction) and "run" in s.name for s in ir_mod.body))

        recovered_ast = JavaIRConverter.from_ir(ir_mod)
        unparsed = lang.unparse(recovered_ast)
        self.assertIn("class Worker", unparsed)
        self.assertIn("run", unparsed)

    def test_go_ir_converter_bidirectional(self) -> None:
        go_code = """
package main

func Add(a int, b int) int {
    c := a + b
    return c
}
"""
        lang = registry.get("go")
        go_ast = lang.parse(go_code)
        ir_mod = GoIRConverter.to_ir(go_ast)

        self.assertEqual(ir_mod.language, "go")
        self.assertTrue(any(isinstance(s, IRFunction) and s.name == "Add" for s in ir_mod.body))

        recovered_ast = GoIRConverter.from_ir(ir_mod)
        unparsed = lang.unparse(recovered_ast)
        self.assertIn("package main", unparsed)
        self.assertIn("func Add", unparsed)


class TestIRControlFlowGraph(unittest.TestCase):
    """Tests CFG construction, dominance, reachability, and loop detection on Common IR."""

    def test_cfg_basic_branching_and_reachability(self) -> None:
        fn = IRFunction(
            name="check_val",
            parameters=["x"],
            body=[
                IRBranch(
                    condition=IRBinaryOperation(op=">", left=IRVariable(name="x"), right=IRConstant(value=0)),
                    body=[IRReturn(value=IRConstant(value=1))],
                    orelse=[IRReturn(value=IRConstant(value=-1))],
                ),
                # Unreachable statement post-branch
                IRAssignment(target=IRVariable(name="dead"), value=IRConstant(value=999)),
            ],
        )

        cfg = IRCFG.build_from_function(fn)
        self.assertGreater(len(cfg.blocks), 2)

        reachable = cfg.reachable_blocks()
        unreachable = cfg.unreachable_blocks()
        self.assertIn(cfg.entry_block.block_id, reachable)
        self.assertIn(cfg.exit_block.block_id, reachable)

        dom = cfg.compute_dominators()
        self.assertIn(cfg.entry_block.block_id, dom[cfg.entry_block.block_id])

        idom = cfg.compute_immediate_dominators()
        self.assertIsNone(idom[cfg.entry_block.block_id])

        ascii_art = cfg.to_ascii()
        self.assertIn("=== IR CFG: check_val ===", ascii_art)
        self.assertIn("true_branch", ascii_art)
        self.assertIn("false_branch", ascii_art)

    def test_cfg_loop_detection(self) -> None:
        fn = IRFunction(
            name="loop_demo",
            parameters=["n"],
            body=[
                IRAssignment(target=IRVariable(name="i"), value=IRConstant(value=0)),
                IRLoop(
                    condition=IRBinaryOperation(op="<", left=IRVariable(name="i"), right=IRVariable(name="n")),
                    body=[
                        IRAssignment(
                            target=IRVariable(name="i"),
                            value=IRBinaryOperation(op="+", left=IRVariable(name="i"), right=IRConstant(value=1)),
                        )
                    ],
                ),
                IRReturn(value=IRVariable(name="i")),
            ],
        )

        cfg = IRCFG.build_from_function(fn)
        loops = cfg.detect_loops()
        self.assertGreaterEqual(len(loops), 1)
        self.assertIn("header", loops[0])
        self.assertIn("latch", loops[0])


class TestUniversalIRPasses(unittest.TestCase):
    """Tests language-independent deobfuscation passes operating directly on Common IR."""

    def test_ir_expression_folding(self) -> None:
        tracker = ProvenanceTracker()
        pass_instance = IRExpressionFolding()

        mod = IRModule(
            body=[
                IRAssignment(
                    target=IRVariable(name="x"),
                    value=IRBinaryOperation(
                        op="+",
                        left=IRConstant(value=10),
                        right=IRBinaryOperation(op="*", left=IRConstant(value=5), right=IRConstant(value=4)),
                    ),
                ),
                IRAssignment(
                    target=IRVariable(name="s"),
                    value=IRBinaryOperation(
                        op="+",
                        left=IRString(value="Hello, "),
                        right=IRString(value="World!"),
                    ),
                ),
                IRAssignment(
                    target=IRVariable(name="b"),
                    value=IRUnaryOperation(op="not", operand=IRConstant(value=False)),
                ),
            ]
        )

        folded = pass_instance.run(mod, tracker)
        self.assertEqual(folded.body[0].value.value, 30)
        self.assertEqual(folded.body[1].value.value, "Hello, World!")
        self.assertTrue(folded.body[2].value.value)
        self.assertGreater(len(tracker.records), 0)

    def test_ir_constant_propagation(self) -> None:
        tracker = ProvenanceTracker()
        pass_instance = IRConstantPropagation()

        fn = IRFunction(
            name="test_const",
            parameters=["param"],
            body=[
                IRAssignment(target=IRVariable(name="a"), value=IRConstant(value=42)),
                IRAssignment(
                    target=IRVariable(name="b"),
                    value=IRBinaryOperation(op="+", left=IRVariable(name="a"), right=IRVariable(name="param")),
                ),
            ],
        )
        mod = IRModule(body=[fn])

        transformed = pass_instance.run(mod, tracker)
        fn_transformed = transformed.body[0]
        # a should be propagated to 42, but param must remain shielded
        b_assign = fn_transformed.body[1]
        self.assertIsInstance(b_assign.value.left, IRConstant)
        self.assertEqual(b_assign.value.left.value, 42)
        self.assertIsInstance(b_assign.value.right, IRVariable)
        self.assertEqual(b_assign.value.right.name, "param")

    def test_ir_dead_code_elimination(self) -> None:
        tracker = ProvenanceTracker()
        pass_instance = IRDeadCodeElimination()

        fn = IRFunction(
            name="test_dead",
            body=[
                IRBranch(
                    condition=IRConstant(value=True),
                    body=[IRAssignment(target=IRVariable(name="live"), value=IRConstant(value=1))],
                    orelse=[IRAssignment(target=IRVariable(name="dead"), value=IRConstant(value=2))],
                ),
                IRReturn(value=IRVariable(name="live")),
                IRAssignment(target=IRVariable(name="unreachable"), value=IRConstant(value=3)),
            ],
        )
        mod = IRModule(body=[fn])

        cleaned = pass_instance.run(mod, tracker)
        fn_cleaned = cleaned.body[0]
        # Branch with True should be replaced with its body, and unreachable statement after return eliminated
        self.assertEqual(len(fn_cleaned.body), 2)
        self.assertEqual(fn_cleaned.body[0].target.name, "live")
        self.assertIsInstance(fn_cleaned.body[1], IRReturn)

    def test_ir_string_reconstruction_and_decoders(self) -> None:
        mod = IRModule(
            body=[
                IRAssignment(
                    target=IRVariable(name="token"),
                    value=IRCall(callee=IRVariable(name="atob"), args=[IRString(value="SGVsbG8gV29ybGQ=")]),
                ),
                IRAssignment(
                    target=IRVariable(name="char_str"),
                    value=IRCall(
                        callee=IRMemberAccess(target=IRVariable(name="String"), member="fromCharCode"),
                        args=[IRConstant(value=71), IRConstant(value=111)],
                    ),
                ),
                IRAssignment(
                    target=IRVariable(name="joined"),
                    value=IRCall(
                        callee=IRMemberAccess(
                            target=IRListLiteral(elements=[IRString(value="a"), IRString(value="b")]),
                            member="join",
                        ),
                        args=[IRString(value="-")],
                    ),
                ),
            ]
        )

        optimized = optimize_ir(mod)
        self.assertEqual(optimized.body[0].value.value, "Hello World")
        self.assertEqual(optimized.body[1].value.value, "Go")
        self.assertEqual(optimized.body[2].value.value, "a-b")


class TestIRPipelineAndCLI(unittest.TestCase):
    """Tests the unified IRPipeline execution, convergence, and CLI commands."""

    def test_ir_pipeline_execution(self) -> None:
        pipeline = IRPipeline()
        mod = IRModule(
            body=[
                IRAssignment(target=IRVariable(name="x"), value=IRBinaryOperation(op="+", left=IRConstant(value=10), right=IRConstant(value=20))),
                IRAssignment(target=IRVariable(name="y"), value=IRBinaryOperation(op="*", left=IRVariable(name="x"), right=IRConstant(value=2))),
            ]
        )

        result = pipeline.execute(mod, max_iterations=3)
        self.assertEqual(result.body[0].value.value, 30)
        self.assertEqual(result.body[1].value.value, 60)
        report = pipeline.generate_report("text")
        self.assertIn("Total transformations applied:", report)

    def test_cli_ir_command(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = main.main(["ir", "tests/samples/simple.py"])
            self.assertEqual(exit_code, 0)
            self.assertIn("module <python>", fake_out.getvalue())

    def test_cli_ir_optimize_command(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = main.main(["ir", "tests/samples/javascript_obfuscated.js", "-O"])
            self.assertEqual(exit_code, 0)
            output = fake_out.getvalue()
            self.assertIn("Bearer token_secret_12345", output)
            self.assertIn("Universal Deobfuscator", output)

    def test_cli_ir_cfg_command(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = main.main(["ir", "tests/samples/simple.py", "--cfg"])
            self.assertEqual(exit_code, 0)
            self.assertIn("=== IR CFG: greeting ===", fake_out.getvalue())

    def test_cli_deobfuscate_use_ir(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = main.main(["deobfuscate", "tests/samples/javascript_obfuscated.js", "--use-ir"])
            self.assertEqual(exit_code, 0)
            output = fake_out.getvalue()
            self.assertIn("Bearer token_secret_12345", output)
            self.assertIn("Universal Deobfuscator", output)


if __name__ == "__main__":
    unittest.main()
