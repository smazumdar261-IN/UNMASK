"""Tests for Go language support (Phase 9).

Per Section 15 and Section 16 of the Master Specification:
Verifies:
- Go lexer (tokens, literals, comments, operators, ASI semicolon insertion)
- Go source parser (compilation units, declarations, functions, statements, expressions)
- Go pretty printer (unparsing AST back to formatted Go code)
- Common IR integration (bidirectional conversion: Go AST <-> Common IR)
- Go deobfuscation passes:
  - Constant propagation
  - Expression folding
  - String reconstruction
  - Decoder evaluation (base64, hex, strconv, strings)
  - Dead code elimination (if(false), unreachable post-return statements)
- Full pipeline integration and confidence scoring
"""

from __future__ import annotations

import unittest

from core.confidence import ConfidenceLevel
from core.exceptions import ParseError
from core.ir import (
    IRAssignment,
    IRBinaryOperation,
    IRCall,
    IRConstant,
    IRFunction,
    IRModule,
    IRReturn,
    IRVariable,
)
from core.pipeline import Pipeline
from core.provenance import ProvenanceTracker
from languages import registry
from languages.go.ast_nodes import (
    GoAssignmentStatement,
    GoBinaryExpression,
    GoBlock,
    GoCallExpression,
    GoCompositeLiteral,
    GoConstSpec,
    GoFile,
    GoForStatement,
    GoFunctionDecl,
    GoIdentifier,
    GoIfStatement,
    GoIndexExpression,
    GoLiteral,
    GoRangeStatement,
    GoReturnStatement,
    GoSelectorExpression,
    GoSliceExpression,
    GoSwitchStatement,
    GoTypeDecl,
    GoUnaryExpression,
    GoVarSpec,
)
from languages.go.ir_converter import GoIRConverter
from languages.go.lexer import GoLexer, GoTokenType
from languages.go.passes.constant_propagation import GoConstantPropagationPass
from languages.go.passes.dead_code import GoDeadCodePass
from languages.go.passes.decoders import GoDecoderDetectionPass
from languages.go.passes.expression_folding import GoExpressionFoldingPass
from languages.go.passes.string_reconstruction import GoStringReconstructionPass
from languages.go.source_parser import GoParser
from languages.go.source_printer import GoPrinter


class TestGoLexer(unittest.TestCase):
    """Test suite for Go lexical analyzer."""

    def test_lexer_tokens_and_asi(self) -> None:
        source = 'package main\nvar x = 42\nconst s = "hello"'
        tokens = GoLexer(source, "main.go").tokenize()
        types = [t.type for t in tokens if t.type != GoTokenType.EOF]

        self.assertEqual(
            types,
            [
                GoTokenType.KEYWORD,      # package
                GoTokenType.IDENTIFIER,   # main
                GoTokenType.PUNCTUATOR,   # ; (ASI)
                GoTokenType.KEYWORD,      # var
                GoTokenType.IDENTIFIER,   # x
                GoTokenType.PUNCTUATOR,   # =
                GoTokenType.NUMBER,       # 42
                GoTokenType.PUNCTUATOR,   # ; (ASI)
                GoTokenType.KEYWORD,      # const
                GoTokenType.IDENTIFIER,   # s
                GoTokenType.PUNCTUATOR,   # =
                GoTokenType.STRING,       # "hello"
                GoTokenType.PUNCTUATOR,   # ; (ASI)
            ],
        )

    def test_numeric_literals(self) -> None:
        source = "0x1A 0b1010 0o77 123 3.14 1_000_000"
        tokens = GoLexer(source).tokenize()
        num_tokens = [t for t in tokens if t.type == GoTokenType.NUMBER]
        self.assertEqual(len(num_tokens), 6)
        self.assertEqual(num_tokens[0].value, "0x1A")
        self.assertEqual(num_tokens[1].value, "0b1010")
        self.assertEqual(num_tokens[2].value, "0o77")
        self.assertEqual(num_tokens[3].value, "123")
        self.assertEqual(num_tokens[4].value, "3.14")
        self.assertEqual(num_tokens[5].value, "1_000_000")

    def test_string_and_rune_literals(self) -> None:
        source = '"hello \\n world" `raw \\n literal` \'a\' \'\\n\''
        tokens = GoLexer(source).tokenize()
        str_tokens = [t for t in tokens if t.type == GoTokenType.STRING]
        rune_tokens = [t for t in tokens if t.type == GoTokenType.RUNE]
        self.assertEqual(len(str_tokens), 2)
        self.assertEqual(str_tokens[0].value, "hello \n world")
        self.assertEqual(str_tokens[1].value, "raw \\n literal")
        self.assertEqual(len(rune_tokens), 2)
        self.assertEqual(rune_tokens[0].value, "a")
        self.assertEqual(rune_tokens[1].value, "\n")

    def test_comments(self) -> None:
        source = "// single line\n/* block\ncomment */\nvar x = 1"
        tokens = GoLexer(source).tokenize()
        val_tokens = [t.value for t in tokens if t.type not in (GoTokenType.EOF, GoTokenType.COMMENT, GoTokenType.PUNCTUATOR)]
        self.assertEqual(val_tokens, ["var", "x", "1"])


class TestGoParser(unittest.TestCase):
    """Test suite for Go source parser."""

    def test_package_and_imports(self) -> None:
        source = """
        package service

        import (
            "fmt"
            alias "strings"
        )
        """
        file_node = GoParser(source).parse()
        self.assertEqual(file_node.package, "service")
        self.assertEqual(len(file_node.imports), 2)
        self.assertEqual(file_node.imports[0].path, "fmt")
        self.assertIsNone(file_node.imports[0].name)
        self.assertEqual(file_node.imports[1].path, "strings")
        self.assertEqual(file_node.imports[1].name, "alias")

    def test_declarations_parsing(self) -> None:
        source = """
        package main

        const Version = 1
        const (
            Host = "localhost"
            Port = 8080
        )

        var counter int = 0
        type MyInt int
        """
        file_node = GoParser(source).parse()
        self.assertEqual(len(file_node.decls), 4)
        self.assertIsInstance(file_node.decls[0], GoConstSpec)
        self.assertEqual(file_node.decls[0].names, ["Version"])
        self.assertIsInstance(file_node.decls[1], GoConstSpec)
        self.assertEqual(file_node.decls[1].names, ["Host", "Port"])
        self.assertIsInstance(file_node.decls[2], GoVarSpec)
        self.assertEqual(file_node.decls[2].names, ["counter"])
        self.assertIsInstance(file_node.decls[3], GoTypeDecl)
        self.assertEqual(file_node.decls[3].name, "MyInt")

    def test_function_and_method_parsing(self) -> None:
        source = """
        package main

        func Add(a int, b int) int {
            return a + b
        }

        func (s *Server) Start() error {
            return nil
        }
        """
        file_node = GoParser(source).parse()
        self.assertEqual(len(file_node.decls), 2)

        fn = file_node.decls[0]
        self.assertIsInstance(fn, GoFunctionDecl)
        self.assertEqual(fn.name, "Add")
        self.assertEqual(len(fn.params), 2)
        self.assertEqual(len(fn.results), 1)
        self.assertEqual(fn.results[0].type_name, "int")

        method = file_node.decls[1]
        self.assertIsInstance(method, GoFunctionDecl)
        self.assertEqual(method.name, "Start")
        self.assertIsNotNone(method.receiver)
        self.assertEqual(method.receiver.name, "s")

    def test_statements_parsing(self) -> None:
        source = """
        package main

        func run() {
            x := 10
            if x > 0 {
                y := 1
            } else {
                y := 2
            }

            for i := 0; i < 5; i++ {
                sum += i
            }

            for k, v := range items {
                process(k, v)
            }

            switch mode {
            case 1:
                break
            default:
                break
            }

            return
        }
        """
        file_node = GoParser(source).parse()
        stmts = file_node.decls[0].body.statements
        self.assertIsInstance(stmts[0], GoAssignmentStatement)
        self.assertIsInstance(stmts[1], GoIfStatement)
        self.assertIsInstance(stmts[2], GoForStatement)
        self.assertIsInstance(stmts[3], GoRangeStatement)
        self.assertIsInstance(stmts[4], GoSwitchStatement)
        self.assertIsInstance(stmts[5], GoReturnStatement)

    def test_expressions_parsing(self) -> None:
        source = """
        package main

        func exprs() {
            a := 10 * (2 + 3)
            b := !(x && y)
            arr := []int{1, 2, 3}
            first := arr[0]
            slice := arr[1:3]
            obj.callMethod(a, b)
        }
        """
        file_node = GoParser(source).parse()
        stmts = file_node.decls[0].body.statements
        self.assertIsInstance(stmts[0].right[0], GoBinaryExpression)
        self.assertIsInstance(stmts[1].right[0], GoUnaryExpression)
        self.assertIsInstance(stmts[2].right[0], GoCompositeLiteral)
        self.assertIsInstance(stmts[3].right[0], GoIndexExpression)
        self.assertIsInstance(stmts[4].right[0], GoSliceExpression)
        self.assertIsInstance(stmts[5].expression, GoCallExpression)

    def test_parse_syntax_error(self) -> None:
        source = "package main\nfunc bad() { x := ; }"
        with self.assertRaises(ParseError) as ctx:
            GoParser(source, "bad.go").parse()
        self.assertIn("Unexpected token", str(ctx.exception))

    def test_pretty_printer_roundtrip(self) -> None:
        source = """
package main

import (
    "fmt"
    "strings"
)

const Message = "Hello, Go!"

func Greet(name string) string {
    return fmt.Sprintf("%s: %s", Message, name)
}
""".strip()
        file_node = GoParser(source).parse()
        printed = GoPrinter.print_code(file_node)
        self.assertIn("package main", printed)
        self.assertIn('"fmt"', printed)
        self.assertIn('const Message = "Hello, Go!"', printed)
        self.assertIn("func Greet(name string) string", printed)
        self.assertIn("return fmt.Sprintf(", printed)


class TestGoIRConverter(unittest.TestCase):
    """Test suite for bidirectional Go AST <-> Common IR conversion."""

    def test_go_ast_to_ir_and_back(self) -> None:
        source = """
        package main

        func Compute(val int) int {
            factor := 10
            res := val * factor
            return res
        }
        """
        file_node = GoParser(source).parse()
        ir_mod = GoIRConverter.to_ir(file_node)

        self.assertIsInstance(ir_mod, IRModule)
        self.assertEqual(ir_mod.language, "go")
        self.assertEqual(len(ir_mod.body), 1)

        ir_fn = ir_mod.body[0]
        self.assertIsInstance(ir_fn, IRFunction)
        self.assertEqual(ir_fn.name, "Compute")
        self.assertEqual(ir_fn.parameters, ["val"])
        self.assertEqual(len(ir_fn.body), 3)

        self.assertIsInstance(ir_fn.body[0], IRAssignment)
        self.assertIsInstance(ir_fn.body[1], IRAssignment)
        self.assertIsInstance(ir_fn.body[2], IRReturn)

        # Convert back from IR to Go AST
        recovered_ast = GoIRConverter.from_ir(ir_mod)
        self.assertIsInstance(recovered_ast, GoFile)
        self.assertEqual(len(recovered_ast.decls), 1)
        fn_decl = recovered_ast.decls[0]
        self.assertIsInstance(fn_decl, GoFunctionDecl)
        self.assertEqual(fn_decl.name, "Compute")
        self.assertEqual(len(fn_decl.body.statements), 3)


class TestGoPasses(unittest.TestCase):
    """Test suite for Go deobfuscation passes."""

    def test_constant_propagation(self) -> None:
        source = """
        package main

        const ApiKey = "SECRET_TOKEN"

        func run() {
            token := ApiKey
            println(token)
        }
        """
        file_node = GoParser(source).parse()
        tracker = ProvenanceTracker()
        res = GoConstantPropagationPass().run(file_node, tracker=tracker)
        src = GoPrinter.print_code(res)

        self.assertIn('println("SECRET_TOKEN")', src)
        self.assertGreater(len(tracker.records), 0)

    def test_constant_propagation_guards_reassignments(self) -> None:
        source = """
        package main

        func run() {
            x := 1
            x = 2
            println(x)
        }
        """
        file_node = GoParser(source).parse()
        tracker = ProvenanceTracker()
        res = GoConstantPropagationPass().run(file_node, tracker=tracker)
        src = GoPrinter.print_code(res)

        # x should not be replaced by 1 because it's reassigned to 2
        self.assertIn("println(x)", src)

    def test_expression_folding_arithmetic_bitwise_and_strings(self) -> None:
        source = """
        package main

        const V1 = 10 * 5 + 4
        const V2 = 0xFF & 0x0F
        const V3 = 0xFF &^ 0x0F
        const V4 = 1 << 4
        const B1 = true && false
        const B2 = !false
        const S1 = "hello " + "world"
        """
        file_node = GoParser(source).parse()
        tracker = ProvenanceTracker()
        res = GoExpressionFoldingPass().run(file_node, tracker=tracker)
        src = GoPrinter.print_code(res)

        self.assertIn("const V1 = 54", src)
        self.assertIn("const V2 = 15", src)
        self.assertIn("const V3 = 240", src)
        self.assertIn("const V4 = 16", src)
        self.assertIn("const B1 = false", src)
        self.assertIn("const B2 = true", src)
        self.assertIn('const S1 = "hello world"', src)

    def test_string_reconstruction_byte_slice_and_join(self) -> None:
        source = """
        package main

        import "strings"

        func run() {
            s1 := string([]byte{71, 111, 108, 97, 110, 103})
            s2 := string([]rune{'O', 'K'})
            s3 := strings.Join([]string{"alpha", "beta"}, "-")
        }
        """
        file_node = GoParser(source).parse()
        tracker = ProvenanceTracker()
        res = GoStringReconstructionPass().run(file_node, tracker=tracker)
        src = GoPrinter.print_code(res)

        self.assertIn('s1 := "Golang"', src)
        self.assertIn('s2 := "OK"', src)
        self.assertIn('s3 := "alpha-beta"', src)

    def test_decoder_detection_base64_and_strconv(self) -> None:
        source = """
        package main

        import (
            "encoding/base64"
            "strconv"
            "strings"
        )

        func run() {
            b64, _ := base64.StdEncoding.DecodeString("SGVsbG8gR28h")
            port, _ := strconv.ParseInt("22B8", 16, 64)
            val, _ := strconv.Atoi("100")
            upper := strings.ToUpper("lowercase")
        }
        """
        file_node = GoParser(source).parse()
        tracker = ProvenanceTracker()
        res = GoDecoderDetectionPass().run(file_node, tracker=tracker)
        src = GoPrinter.print_code(res)

        self.assertIn('b64, _ := "Hello Go!"', src)
        self.assertIn("port, _ := 8888", src)
        self.assertIn("val, _ := 100", src)
        self.assertIn('upper := "LOWERCASE"', src)

    def test_dead_code_elimination(self) -> None:
        source = """
        package main

        func test() int {
            if false {
                println("dead branch")
            }
            if true {
                a := 1
            } else {
                b := 2
            }
            return 42
            c := 3
        }
        """
        file_node = GoParser(source).parse()
        tracker = ProvenanceTracker()
        res = GoDeadCodePass().run(file_node, tracker=tracker)
        src = GoPrinter.print_code(res)

        self.assertNotIn("dead branch", src)
        self.assertNotIn("b := 2", src)
        self.assertNotIn("c := 3", src)
        self.assertIn("return 42", src)

    def test_full_pipeline_convergence_and_audit_report(self) -> None:
        source = """
        package main

        import (
            "encoding/base64"
            "fmt"
            "strconv"
            "strings"
        )

        const RawToken = "U3VwZXJTZWNyZXQ="
        const BasePort = 8000 + 80

        func run() {
            tokenBytes, _ := base64.StdEncoding.DecodeString(RawToken)
            token := string(tokenBytes)
            prefix := strings.Join([]string{"auth", "v1"}, "-")
            port, _ := strconv.ParseInt("1F90", 16, 64)

            if false {
                panic("dead code")
            }

            fmt.Println(token)
            fmt.Println(prefix)
            fmt.Println(BasePort)
            fmt.Println(port)
        }
        """
        file_node = GoParser(source).parse()
        pipeline = Pipeline(min_confidence=ConfidenceLevel.LOW)
        pipeline.add_pass(GoConstantPropagationPass())
        pipeline.add_pass(GoExpressionFoldingPass())
        pipeline.add_pass(GoDecoderDetectionPass())
        pipeline.add_pass(GoStringReconstructionPass())
        pipeline.add_pass(GoDeadCodePass())

        result = pipeline.execute(file_node, max_iterations=5, until_convergence=True)
        final_code = GoPrinter.print_code(result)

        self.assertIn('"SuperSecret"', final_code)
        self.assertIn('"auth-v1"', final_code)
        self.assertIn("const BasePort = 8080", final_code)
        self.assertIn("port, _ := 8080", final_code)
        self.assertNotIn("panic", final_code)

        report = pipeline.generate_report()
        self.assertIn("Universal Deobfuscator Audit Report", report)
        self.assertGreater(pipeline.tracker.get_engine().compute_average_confidence(), 0.9)


if __name__ == "__main__":
    unittest.main()
