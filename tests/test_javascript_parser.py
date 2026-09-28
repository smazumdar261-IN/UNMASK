"""Tests for JavaScript Lexer, Parser, and Printer (Phase 6).

Per Section 12 of the Master Specification:
Verifies parsing of JavaScript ES6+ code, line/col provenance, AST generation,
AST roundtripping via JSPrinter, and syntax error diagnostics.
"""

from __future__ import annotations

import unittest

from core.exceptions import ParseError
from languages import registry
from languages.javascript.ast_nodes import (
    JSArrayExpression,
    JSAssignmentExpression,
    JSBinaryExpression,
    JSBlockStatement,
    JSCallExpression,
    JSFunctionDeclaration,
    JSIdentifier,
    JSIfStatement,
    JSLiteral,
    JSMemberExpression,
    JSObjectExpression,
    JSProgram,
    JSReturnStatement,
    JSUnaryExpression,
    JSVariableDeclaration,
    JSWhileStatement,
)
from languages.javascript.lexer import JSLexer, JSTokenType
from languages.javascript.parser import JSParser
from languages.javascript.printer import JSPrinter


class TestJSLexer(unittest.TestCase):
    """Test suite for JavaScript lexer."""

    def test_lexer_tokens_and_provenance(self) -> None:
        source = "let x = 42; // comment\nconst y = 'hello';"
        tokens = JSLexer(source, "test.js").tokenize()

        # Check token types
        token_types = [t.type for t in tokens if t.type != JSTokenType.EOF]
        self.assertEqual(
            token_types,
            [
                JSTokenType.KEYWORD,      # let
                JSTokenType.IDENTIFIER,   # x
                JSTokenType.PUNCTUATOR,   # =
                JSTokenType.NUMBER,       # 42
                JSTokenType.PUNCTUATOR,   # ;
                JSTokenType.KEYWORD,      # const
                JSTokenType.IDENTIFIER,   # y
                JSTokenType.PUNCTUATOR,   # =
                JSTokenType.STRING,       # 'hello'
                JSTokenType.PUNCTUATOR,   # ;
            ],
        )

        # Check line and column tracking
        let_tok = tokens[0]
        self.assertEqual(let_tok.location.start_line, 1)
        self.assertEqual(let_tok.location.start_col, 1)

        const_tok = tokens[5]
        self.assertEqual(const_tok.location.start_line, 2)
        self.assertEqual(const_tok.location.start_col, 1)

    def test_string_escapes(self) -> None:
        source = r"var a = 'hello\nworld\x21\u0041';"
        tokens = JSLexer(source).tokenize()
        str_tok = next(t for t in tokens if t.type == JSTokenType.STRING)
        self.assertEqual(str_tok.value, "hello\nworld!A")

    def test_multi_char_punctuators(self) -> None:
        source = "a === b && c !== d || e >= f => g"
        tokens = JSLexer(source).tokenize()
        punct_values = [t.value for t in tokens if t.type == JSTokenType.PUNCTUATOR]
        self.assertIn("===", punct_values)
        self.assertIn("&&", punct_values)
        self.assertIn("!==", punct_values)
        self.assertIn("||", punct_values)
        self.assertIn(">=", punct_values)
        self.assertIn("=>", punct_values)

    def test_block_comment_stripping(self) -> None:
        source = "let /* inline comment */ x = /* block */ 100;"
        tokens = JSLexer(source).tokenize()
        values = [t.value for t in tokens if t.type != JSTokenType.EOF]
        self.assertEqual(values, ["let", "x", "=", "100", ";"])


class TestJSParser(unittest.TestCase):
    """Test suite for JavaScript parser."""

    def test_variable_declarations(self) -> None:
        source = "var a = 1; let b = 'two'; const c = true;"
        program = JSParser(source).parse()
        self.assertIsInstance(program, JSProgram)
        self.assertEqual(len(program.body), 3)

        stmt0 = program.body[0]
        self.assertIsInstance(stmt0, JSVariableDeclaration)
        self.assertEqual(stmt0.kind, "var")
        self.assertEqual(stmt0.declarations[0].id.name, "a")
        self.assertEqual(stmt0.declarations[0].init.value, 1)

        stmt1 = program.body[1]
        self.assertIsInstance(stmt1, JSVariableDeclaration)
        self.assertEqual(stmt1.kind, "let")
        self.assertEqual(stmt1.declarations[0].id.name, "b")
        self.assertEqual(stmt1.declarations[0].init.value, "two")

    def test_function_declaration(self) -> None:
        source = "function add(a, b) { return a + b; }"
        program = JSParser(source).parse()
        fn = program.body[0]
        self.assertIsInstance(fn, JSFunctionDeclaration)
        self.assertEqual(fn.id.name, "add")
        self.assertEqual(len(fn.params), 2)
        self.assertEqual(fn.params[0].name, "a")
        self.assertEqual(fn.params[1].name, "b")
        self.assertEqual(len(fn.body.body), 1)
        self.assertIsInstance(fn.body.body[0], JSReturnStatement)

    def test_if_while_statements(self) -> None:
        source = """
        if (x > 0) {
            y = 1;
        } else {
            y = -1;
        }
        while (y < 10) {
            y = y + 1;
        }
        """
        program = JSParser(source).parse()
        self.assertEqual(len(program.body), 2)
        self.assertIsInstance(program.body[0], JSIfStatement)
        self.assertIsInstance(program.body[1], JSWhileStatement)

    def test_calls_and_member_expressions(self) -> None:
        source = "console.log(arr[0], obj['prop']);"
        program = JSParser(source).parse()
        expr_stmt = program.body[0]
        call = expr_stmt.expression
        self.assertIsInstance(call, JSCallExpression)
        self.assertIsInstance(call.callee, JSMemberExpression)
        self.assertFalse(call.callee.computed)
        self.assertEqual(call.callee.property.name, "log")

        # arr[0]
        arg0 = call.arguments[0]
        self.assertIsInstance(arg0, JSMemberExpression)
        self.assertTrue(arg0.computed)
        self.assertEqual(arg0.property.value, 0)

        # obj['prop']
        arg1 = call.arguments[1]
        self.assertIsInstance(arg1, JSMemberExpression)
        self.assertTrue(arg1.computed)
        self.assertEqual(arg1.property.value, "prop")

    def test_array_and_object_expressions(self) -> None:
        source = "let obj = { foo: 'bar', num: 123, list: [1, 2, 3] };"
        program = JSParser(source).parse()
        decl = program.body[0].declarations[0]
        obj = decl.init
        self.assertIsInstance(obj, JSObjectExpression)
        self.assertEqual(len(obj.properties), 3)
        self.assertEqual(obj.properties[0].key.name, "foo")
        self.assertEqual(obj.properties[0].value.value, "bar")

    def test_syntax_error(self) -> None:
        source = "let x = ;"
        with self.assertRaises(ParseError) as ctx:
            JSParser(source, "bad.js").parse()
        self.assertIn("ParseError", str(ctx.exception))
        self.assertEqual(ctx.exception.lineno, 1)


class TestJSPrinter(unittest.TestCase):
    """Test suite for JavaScript unparser / code generator."""

    def test_roundtrip_simple(self) -> None:
        source = "var x = 10;\nvar y = x + 20;"
        tree = JSParser(source).parse()
        out = JSPrinter.print_code(tree)
        self.assertIn("var x = 10;", out)
        self.assertIn("var y = x + 20;", out)

    def test_roundtrip_function(self) -> None:
        source = "function greet(name) {\n    return 'Hello ' + name;\n}"
        tree = JSParser(source).parse()
        out = JSPrinter.print_code(tree)
        self.assertIn("function greet(name)", out)
        self.assertIn("return 'Hello ' + name;", out)

    def test_language_registry_integration(self) -> None:
        js_lang = registry.detect_language("script.js")
        self.assertIsNotNone(js_lang)
        self.assertEqual(js_lang.name, "javascript")

        mjs_lang = registry.detect_language("module.mjs")
        self.assertIsNotNone(mjs_lang)
        self.assertEqual(mjs_lang.name, "javascript")

        source = "const greeting = 'hello';"
        tree = js_lang.parse(source)
        unparsed = js_lang.unparse(tree)
        self.assertIn("const greeting = 'hello';", unparsed)


if __name__ == "__main__":
    unittest.main()
