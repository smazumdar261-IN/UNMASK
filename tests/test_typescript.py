"""Tests for TypeScript support (Phase 7).

Per Section 13 of the Master Specification:
Verifies:
- TypeScript parser preserving interfaces, types, enums, generics, decorators
- Type annotations on variables, parameters, return types, and type assertions (as)
- TypeScript printer preserving TypeScript source vs compiling to JavaScript output
- Full deobfuscation pipeline integration on TypeScript
"""

from __future__ import annotations

import unittest

from core.confidence import ConfidenceLevel
from core.pipeline import Pipeline
from core.provenance import ProvenanceTracker
from languages import registry
from languages.javascript.passes.constant_propagation import JSConstantPropagationPass
from languages.javascript.passes.decoders import JSDecoderDetectionPass
from languages.javascript.passes.expression_folding import JSExpressionFoldingPass
from languages.javascript.passes.iife_normalization import JSIIFENormalizationPass
from languages.javascript.passes.property_normalization import JSPropertyNormalizationPass
from languages.javascript.passes.string_reconstruction import JSStringReconstructionPass
from languages.typescript.ast_nodes import (
    TSAsExpression,
    TSDecorator,
    TSEnumDeclaration,
    TSInterfaceDeclaration,
    TSTypeAliasDeclaration,
)
from languages.typescript.parser import TSParser
from languages.typescript.printer import TSPrinter


class TestTSParser(unittest.TestCase):
    """Test suite for TypeScript parser."""

    def test_interface_declaration(self) -> None:
        source = """
        interface User<T> extends BaseEntity {
            readonly id: string;
            name?: string;
            metadata: T;
            save(force: boolean): void;
        }
        """
        program = TSParser(source).parse()
        self.assertEqual(len(program.body), 1)
        iface = program.body[0]
        self.assertIsInstance(iface, TSInterfaceDeclaration)
        self.assertEqual(iface.id.name, "User")
        self.assertIsNotNone(iface.type_parameters)
        self.assertEqual(iface.type_parameters.params[0].name, "T")
        self.assertEqual(len(iface.extends), 1)
        self.assertEqual(iface.extends[0].name, "BaseEntity")
        self.assertEqual(len(iface.body), 4)

    def test_type_alias_declaration(self) -> None:
        source = "type ID<T> = string | number | T;"
        program = TSParser(source).parse()
        self.assertEqual(len(program.body), 1)
        alias = program.body[0]
        self.assertIsInstance(alias, TSTypeAliasDeclaration)
        self.assertEqual(alias.id.name, "ID")
        self.assertEqual(alias.type_parameters.params[0].name, "T")
        self.assertIn("string | number | T", alias.type_annotation.raw)

    def test_enum_declaration(self) -> None:
        source = """
        enum Color {
            Red = 1,
            Green = 2,
            Blue = 3
        }
        const enum Direction {
            Up,
            Down
        }
        """
        program = TSParser(source).parse()
        self.assertEqual(len(program.body), 2)
        enum1 = program.body[0]
        self.assertIsInstance(enum1, TSEnumDeclaration)
        self.assertEqual(enum1.id.name, "Color")
        self.assertFalse(enum1.is_const)
        self.assertEqual(len(enum1.members), 3)

        enum2 = program.body[1]
        self.assertIsInstance(enum2, TSEnumDeclaration)
        self.assertEqual(enum2.id.name, "Direction")
        self.assertTrue(enum2.is_const)

    def test_generic_function_with_types(self) -> None:
        source = "function identity<T>(arg: T): T { return arg; }"
        program = TSParser(source).parse()
        fn = program.body[0]
        self.assertEqual(fn.id.name, "identity")
        self.assertIsNotNone(fn.type_parameters)
        self.assertEqual(fn.type_parameters.params[0].name, "T")
        self.assertIsNotNone(fn.return_type)
        self.assertEqual(fn.return_type.raw, "T")

    def test_variable_type_annotation(self) -> None:
        source = "const greeting: string = 'hello'; let count: number = 42;"
        program = TSParser(source).parse()
        self.assertEqual(len(program.body), 2)
        decl1 = program.body[0].declarations[0]
        self.assertEqual(decl1.id.name, "greeting")
        self.assertEqual(decl1.type_annotation.raw, "string")

        decl2 = program.body[1].declarations[0]
        self.assertEqual(decl2.id.name, "count")
        self.assertEqual(decl2.type_annotation.raw, "number")

    def test_as_type_assertion(self) -> None:
        source = "const val = rawData as string;"
        program = TSParser(source).parse()
        init = program.body[0].declarations[0].init
        self.assertIsInstance(init, TSAsExpression)
        self.assertEqual(init.expression.name, "rawData")
        self.assertEqual(init.type_annotation.raw, "string")

    def test_decorators(self) -> None:
        source = """
        @logged
        function doWork() {
            return 1;
        }
        """
        program = TSParser(source).parse()
        fn = program.body[0]
        self.assertEqual(len(fn.decorators), 1)
        self.assertIsInstance(fn.decorators[0], TSDecorator)
        self.assertEqual(fn.decorators[0].expression.name, "logged")


class TestTSPrinter(unittest.TestCase):
    """Test suite for TypeScript printer and source vs JS output distinguishing."""

    def test_preserve_typescript_constructs(self) -> None:
        source = """interface Person {
    name: string;
    age?: number;
}
type StringOrNum = string | number;
enum Status {
    Active = 1,
    Inactive = 0,
}
function greet<T>(val: T): T {
    return val;
}"""
        tree = TSParser(source).parse()
        ts_output = TSPrinter.print_code(tree, target_js=False)

        # Assert all TS features are preserved in TypeScript mode
        self.assertIn("interface Person {", ts_output)
        self.assertIn("name: string;", ts_output)
        self.assertIn("type StringOrNum = string | number;", ts_output)
        self.assertIn("enum Status {", ts_output)
        self.assertIn("function greet<T>(val: T): T", ts_output)

    def test_distinguish_javascript_output(self) -> None:
        source = """interface Person {
    name: string;
}
type StringOrNum = string | number;
enum Status {
    Active = 1,
    Inactive = 0,
}
let greeting: string = 'hello';
function greet<T>(val: T): T {
    return val as any;
}"""
        tree = TSParser(source).parse()
        js_output = TSPrinter.print_code(tree, target_js=True)

        # Assert types and interfaces are stripped for JS output
        self.assertNotIn("interface Person", js_output)
        self.assertNotIn("type StringOrNum", js_output)
        self.assertNotIn(": string", js_output)
        self.assertNotIn("<T>", js_output)
        self.assertNotIn("as any", js_output)

        # Enum should be translated to JS dictionary
        self.assertIn("var Status = { Active: 1, Inactive: 0 };", js_output)
        self.assertIn("let greeting = 'hello';", js_output)
        self.assertIn("function greet(val) {", js_output)

    def test_registry_detection(self) -> None:
        ts_lang = registry.detect_language("app.ts")
        self.assertIsNotNone(ts_lang)
        self.assertEqual(ts_lang.name, "typescript")

        tsx_lang = registry.detect_language("component.tsx")
        self.assertIsNotNone(tsx_lang)
        self.assertEqual(tsx_lang.name, "typescript")


class TestTSDeobfuscationIntegration(unittest.TestCase):
    """Test suite for TypeScript deobfuscation pipeline."""

    def test_typescript_pipeline_preserves_types_and_deobfuscates(self) -> None:
        source = """
        interface Config {
            token: string;
            name: string;
            offset: number;
        }
        enum Role {
            Admin = 1,
            User = 2,
        }
        const rawToken: string = atob('c2VjcmV0X3Rva2VuXzEyMw==');
        const appName: string = String.fromCharCode(84, 83, 65, 112, 112);
        const calcOffset: number = 10 + 20 * 2;
        console['log'](rawToken, appName, calcOffset);
        """
        tree = TSParser(source).parse()

        pipeline = Pipeline()
        pipeline.add_pass(JSConstantPropagationPass())
        pipeline.add_pass(JSDecoderDetectionPass())
        pipeline.add_pass(JSStringReconstructionPass())
        pipeline.add_pass(JSExpressionFoldingPass())
        pipeline.add_pass(JSPropertyNormalizationPass())
        pipeline.add_pass(JSIIFENormalizationPass())

        result = pipeline.execute(tree, max_iterations=10, until_convergence=True)

        # 1. Output as TypeScript (types preserved)
        ts_output = TSPrinter.print_code(result, target_js=False)
        self.assertIn("interface Config {", ts_output)
        self.assertIn("enum Role {", ts_output)
        self.assertIn("const rawToken: string = 'secret_token_123';", ts_output)
        self.assertIn("const appName: string = 'TSApp';", ts_output)
        self.assertIn("const calcOffset: number = 50;", ts_output)
        self.assertIn("console.log('secret_token_123', 'TSApp', 50);", ts_output)

        # 2. Output as JavaScript (clean JS without TS types)
        js_output = TSPrinter.print_code(result, target_js=True)
        self.assertNotIn("interface Config", js_output)
        self.assertNotIn(": string", js_output)
        self.assertNotIn(": number", js_output)
        self.assertIn("const rawToken = 'secret_token_123';", js_output)
        self.assertIn("const appName = 'TSApp';", js_output)
        self.assertIn("console.log('secret_token_123', 'TSApp', 50);", js_output)


if __name__ == "__main__":
    unittest.main()
