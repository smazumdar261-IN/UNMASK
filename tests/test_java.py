"""Tests for Java language support (Phase 8).

Per Section 14 and Section 16 of the Master Specification:
Verifies:
- Java lexer (tokens, literals, comments, operators, Unicode escapes)
- Java source parser (compilation units, classes, interfaces, methods, fields, statements, expressions)
- Java pretty printer (unparsing AST back to formatted Java code)
- Pure-Python JVM bytecode reader and decompiler (.class and .jar archives)
- Common IR integration (bidirectional conversion: Java AST <-> Common IR)
- Java deobfuscation passes:
  - Constant propagation
  - Expression folding
  - Decoder evaluation (Base64, Integer.parseInt, string transforms)
  - String reconstruction (byte/char arrays, StringBuilder chains)
  - Dead code elimination (if(false), unreachable post-return statements)
- Full pipeline integration and confidence scoring
"""

from __future__ import annotations

import io
import struct
import unittest
import zipfile

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
from languages.java.ast_nodes import (
    JavaArrayAccess,
    JavaAssignmentExpression,
    JavaBinaryExpression,
    JavaBlock,
    JavaCastExpression,
    JavaClassDeclaration,
    JavaCompilationUnit,
    JavaExpressionStatement,
    JavaFieldAccess,
    JavaFieldDeclaration,
    JavaIdentifier,
    JavaIfStatement,
    JavaImportDeclaration,
    JavaInterfaceDeclaration,
    JavaLiteral,
    JavaMethodCall,
    JavaMethodDeclaration,
    JavaNewArrayExpression,
    JavaNewClassExpression,
    JavaPackageDeclaration,
    JavaReturnStatement,
    JavaUnaryExpression,
    JavaVariableDeclarationStatement,
    JavaWhileStatement,
)
from languages.java.bytecode import BytecodeDecompiler, ClassFileReader
from languages.java.ir_converter import JavaIRConverter
from languages.java.lexer import JavaLexer, JavaTokenType
from languages.java.passes.constant_propagation import JavaConstantPropagationPass
from languages.java.passes.dead_code import JavaDeadCodePass
from languages.java.passes.decoders import JavaDecoderDetectionPass
from languages.java.passes.expression_folding import JavaExpressionFoldingPass
from languages.java.passes.string_reconstruction import JavaStringReconstructionPass
from languages.java.source_parser import JavaParser
from languages.java.source_printer import JavaPrinter


class TestJavaLexer(unittest.TestCase):
    """Test suite for Java lexical analyzer."""

    def test_lexer_tokens_and_provenance(self) -> None:
        source = 'public class Hello {\n    int x = 42;\n    String s = "world";\n}'
        tokens = JavaLexer(source, "Hello.java").tokenize()
        types = [t.type for t in tokens if t.type != JavaTokenType.EOF]

        self.assertEqual(
            types,
            [
                JavaTokenType.KEYWORD,      # public
                JavaTokenType.KEYWORD,      # class
                JavaTokenType.IDENTIFIER,   # Hello
                JavaTokenType.PUNCTUATOR,   # {
                JavaTokenType.KEYWORD,      # int
                JavaTokenType.IDENTIFIER,   # x
                JavaTokenType.PUNCTUATOR,   # =
                JavaTokenType.NUMBER,       # 42
                JavaTokenType.PUNCTUATOR,   # ;
                JavaTokenType.IDENTIFIER,   # String
                JavaTokenType.IDENTIFIER,   # s
                JavaTokenType.PUNCTUATOR,   # =
                JavaTokenType.STRING,       # "world"
                JavaTokenType.PUNCTUATOR,   # ;
                JavaTokenType.PUNCTUATOR,   # }
            ],
        )

    def test_numeric_literals(self) -> None:
        source = "0x1A 0b1010 077 123L 3.14f 2.5d"
        tokens = JavaLexer(source).tokenize()
        num_tokens = [t for t in tokens if t.type == JavaTokenType.NUMBER]
        self.assertEqual(len(num_tokens), 6)
        self.assertEqual(num_tokens[0].value, "0x1A")
        self.assertEqual(num_tokens[1].value, "0b1010")
        self.assertEqual(num_tokens[2].value, "077")
        self.assertEqual(num_tokens[3].value, "123L")
        self.assertEqual(num_tokens[4].value, "3.14f")
        self.assertEqual(num_tokens[5].value, "2.5d")

    def test_char_and_string_literals(self) -> None:
        source = "'a' '\\n' \"hello \\\"world\\\"\""
        tokens = JavaLexer(source).tokenize()
        char_tokens = [t for t in tokens if t.type == JavaTokenType.CHAR]
        str_tokens = [t for t in tokens if t.type == JavaTokenType.STRING]
        self.assertEqual(len(char_tokens), 2)
        self.assertEqual(char_tokens[0].value, "a")
        self.assertEqual(char_tokens[1].value, "\n")
        self.assertEqual(len(str_tokens), 1)
        self.assertEqual(str_tokens[0].value, 'hello "world"')

    def test_unicode_escapes(self) -> None:
        source = 'String s = "\\u0048\\u0065\\u006C\\u006C\\u006F";'
        tokens = JavaLexer(source).tokenize()
        str_tok = [t for t in tokens if t.type == JavaTokenType.STRING][0]
        self.assertEqual(str_tok.value, "Hello")

    def test_comments(self) -> None:
        source = "// single line\n/* multi\nline */\n/** javadoc */\nint a = 1;"
        tokens = JavaLexer(source).tokenize()
        non_eof = [t for t in tokens if t.type != JavaTokenType.EOF]
        self.assertEqual(len(non_eof), 5)  # int, a, =, 1, ;


class TestJavaParser(unittest.TestCase):
    """Test suite for Java source parser."""

    def test_package_and_imports(self) -> None:
        source = """
        package com.example.service;
        import java.util.List;
        import static java.lang.Math.PI;

        public class MyService {}
        """
        unit = JavaParser(source).parse()
        self.assertIsNotNone(unit.package)
        self.assertEqual(unit.package.name, "com.example.service")
        self.assertEqual(len(unit.imports), 2)
        self.assertEqual(unit.imports[0].name, "java.util.List")
        self.assertFalse(unit.imports[0].is_static)
        self.assertEqual(unit.imports[1].name, "java.lang.Math.PI")
        self.assertTrue(unit.imports[1].is_static)

    def test_class_and_interface_declarations(self) -> None:
        source = """
        public interface Worker {
            void work();
        }

        public abstract class BaseWorker implements Worker {
            protected String name;
            public abstract void doTask();
        }
        """
        unit = JavaParser(source).parse()
        self.assertEqual(len(unit.types), 2)
        iface = unit.types[0]
        self.assertIsInstance(iface, JavaInterfaceDeclaration)
        self.assertEqual(iface.name, "Worker")
        self.assertEqual(len(iface.members), 1)

        cls_decl = unit.types[1]
        self.assertIsInstance(cls_decl, JavaClassDeclaration)
        self.assertEqual(cls_decl.name, "BaseWorker")
        self.assertIn("abstract", cls_decl.modifiers)
        self.assertIn("Worker", cls_decl.interfaces)
        self.assertEqual(len(cls_decl.members), 2)

    def test_method_and_field_parsing(self) -> None:
        source = """
        public class Calculator {
            public static final int VERSION = 1;

            public int add(int a, int b) {
                return a + b;
            }
        }
        """
        unit = JavaParser(source).parse()
        cls_decl = unit.types[0]
        field = cls_decl.members[0]
        self.assertIsInstance(field, JavaFieldDeclaration)
        self.assertEqual(field.name, "VERSION")
        self.assertIn("final", field.modifiers)
        self.assertIsInstance(field.initializer, JavaLiteral)
        self.assertEqual(field.initializer.value, 1)

        method = cls_decl.members[1]
        self.assertIsInstance(method, JavaMethodDeclaration)
        self.assertEqual(method.name, "add")
        self.assertEqual(method.return_type, "int")
        self.assertEqual(len(method.parameters), 2)
        self.assertEqual(method.parameters[0].name, "a")
        self.assertEqual(method.parameters[1].name, "b")

    def test_control_flow_statements(self) -> None:
        source = """
        public class Flow {
            public void test() {
                if (x > 0) {
                    y = 1;
                } else {
                    y = 2;
                }

                while (count < 10) {
                    count = count + 1;
                }

                return;
            }
        }
        """
        unit = JavaParser(source).parse()
        stmts = unit.types[0].members[0].body.statements
        self.assertIsInstance(stmts[0], JavaIfStatement)
        self.assertIsInstance(stmts[1], JavaWhileStatement)
        self.assertIsInstance(stmts[2], JavaReturnStatement)

    def test_expressions_parsing(self) -> None:
        source = """
        public class Exprs {
            public void run() {
                int a = 10 * (2 + 3);
                boolean b = !(x && y);
                int d = (int) 3.14;
                int[] arr = new int[5];
                int first = arr[0];
                obj.callMethod(a, b);
            }
        }
        """
        unit = JavaParser(source).parse()
        stmts = unit.types[0].members[0].body.statements
        # binary
        self.assertIsInstance(stmts[0].initializer, JavaBinaryExpression)
        # unary
        self.assertIsInstance(stmts[1].initializer, JavaUnaryExpression)
        # cast
        self.assertIsInstance(stmts[2].initializer, JavaCastExpression)
        # array creation
        self.assertIsInstance(stmts[3].initializer, JavaNewArrayExpression)
        # array access
        self.assertIsInstance(stmts[4].initializer, JavaArrayAccess)
        # method call
        self.assertIsInstance(stmts[5].expression, JavaMethodCall)

    def test_parse_syntax_error(self) -> None:
        source = "public class Bad { int x = ; }"
        with self.assertRaises(ParseError) as ctx:
            JavaParser(source, "Bad.java").parse()
        self.assertIn("Unexpected token", str(ctx.exception))

    def test_pretty_printer_roundtrip(self) -> None:
        source = """
package com.demo;

public class Sample {
    private int x = 42;

    public int getX() {
        return this.x;
    }
}
""".strip()
        unit = JavaParser(source).parse()
        printed = JavaPrinter.print_code(unit)
        self.assertIn("package com.demo;", printed)
        self.assertIn("public class Sample", printed)
        self.assertIn("private int x = 42;", printed)
        self.assertIn("public int getX()", printed)
        self.assertIn("return this.x;", printed)


def create_synthetic_class_bytes(
    class_name: str,
    method_name: str = "compute",
    bytecode: bytes = bytes([0x10, 42, 0xAC]),  # bipush 42, ireturn
    return_type_desc: str = "()I",
) -> bytes:
    """Constructs valid binary JVM .class bytes for testing pure-Python bytecode reader."""
    cp: list[bytes] = []

    def add_utf8(s: str) -> int:
        encoded = s.encode("utf-8")
        cp.append(b"\x01" + struct.pack(">H", len(encoded)) + encoded)
        return len(cp)

    def add_class(name_idx: int) -> int:
        cp.append(b"\x07" + struct.pack(">H", name_idx))
        return len(cp)

    u_this = add_utf8(class_name.replace(".", "/"))
    c_this = add_class(u_this)
    u_super = add_utf8("java/lang/Object")
    c_super = add_class(u_super)
    u_mname = add_utf8(method_name)
    u_mdesc = add_utf8(return_type_desc)
    u_code = add_utf8("Code")

    code_data = struct.pack(">HHI", 4, 2, len(bytecode)) + bytecode + struct.pack(">HH", 0, 0)
    code_attr = struct.pack(">HI", u_code, len(code_data)) + code_data

    method = struct.pack(">HHH", 0x0009, u_mname, u_mdesc) + struct.pack(">H", 1) + code_attr

    header = struct.pack(">IHHH", 0xCAFEBABE, 0, 52, len(cp) + 1)
    cp_bytes = b"".join(cp)
    cls_meta = struct.pack(">HHHHHH", 0x0001, c_this, c_super, 0, 0, 1) + method + struct.pack(">H", 0)
    return header + cp_bytes + cls_meta


class TestJavaBytecode(unittest.TestCase):
    """Test suite for JVM bytecode reading and decompilation (Phase 8 Bytecode mode)."""

    def test_class_file_reader(self) -> None:
        raw_bytes = create_synthetic_class_bytes("com.example.TestClass")
        reader = ClassFileReader(raw_bytes, "TestClass.class")
        self.assertEqual(reader.this_class, "com.example.TestClass")
        self.assertEqual(reader.super_class, "java.lang.Object")
        self.assertEqual(len(reader.methods), 1)
        self.assertEqual(reader.methods[0]["name"], "compute")

    def test_bytecode_decompilation_constants_and_arithmetic(self) -> None:
        # iconst_5 (0x08), bipush 10 (0x10, 10), iadd (0x60), ireturn (0xAC)
        bc = bytes([0x08, 0x10, 10, 0x60, 0xAC])
        raw_bytes = create_synthetic_class_bytes("Calc", method_name="add", bytecode=bc)
        reader = ClassFileReader(raw_bytes)
        unit = BytecodeDecompiler(reader).decompile()
        src = JavaPrinter.print_code(unit)
        self.assertIn("public class Calc", src)
        self.assertIn("public static int add()", src)
        self.assertIn("return 5 + 10;", src)

    def test_jar_archive_decompilation(self) -> None:
        raw_bytes = create_synthetic_class_bytes("com.demo.App", method_name="run")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("com/demo/App.class", raw_bytes)
            zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        jar_data = buf.getvalue()

        lang = registry.get("java-bytecode")
        unit = lang.parse(jar_data, filename="app.jar")
        self.assertIsInstance(unit, JavaCompilationUnit)
        src = JavaPrinter.print_code(unit)
        self.assertIn("package com.demo;", src)
        self.assertIn("public class App", src)
        self.assertIn("public static int run()", src)

    def test_registry_file_extension_detection(self) -> None:
        self.assertEqual(registry.detect_language("Main.java").name, "java")
        self.assertEqual(registry.detect_language("Main.class").name, "java-bytecode")
        self.assertEqual(registry.detect_language("archive.jar").name, "java-bytecode")


class TestJavaIRConverter(unittest.TestCase):
    """Test suite for bidirectional Java AST <-> Common IR conversion."""

    def test_java_ast_to_ir_and_back(self) -> None:
        source = """
        package com.test;

        public class Processor {
            public static int process(int input) {
                int factor = 10;
                int result = input * factor;
                return result;
            }
        }
        """
        unit = JavaParser(source).parse()
        ir_mod = JavaIRConverter.to_ir(unit)

        self.assertIsInstance(ir_mod, IRModule)
        self.assertEqual(ir_mod.language, "java")
        self.assertEqual(len(ir_mod.body), 1)

        ir_fn = ir_mod.body[0]
        self.assertIsInstance(ir_fn, IRFunction)
        self.assertEqual(ir_fn.name, "Processor.process")
        self.assertEqual(ir_fn.parameters, ["input"])
        self.assertEqual(len(ir_fn.body), 3)

        self.assertIsInstance(ir_fn.body[0], IRAssignment)
        self.assertIsInstance(ir_fn.body[1], IRAssignment)
        self.assertIsInstance(ir_fn.body[2], IRReturn)

        # Convert IR back to Java AST
        recovered_ast = JavaIRConverter.from_ir(ir_mod)
        self.assertIsInstance(recovered_ast, JavaCompilationUnit)
        self.assertEqual(len(recovered_ast.types), 1)
        self.assertEqual(recovered_ast.types[0].name, "Processor")
        self.assertEqual(len(recovered_ast.types[0].members), 1)
        m = recovered_ast.types[0].members[0]
        self.assertEqual(m.name, "process")
        self.assertEqual(len(m.body.statements), 3)


class TestJavaPasses(unittest.TestCase):
    """Test suite for Java deobfuscation passes."""

    def test_constant_propagation(self) -> None:
        source = """
        public class Config {
            public static final String API_KEY = "SECRET_123";

            public void printKey() {
                String localKey = API_KEY;
                System.out.println(localKey);
            }
        }
        """
        unit = JavaParser(source).parse()
        tracker = ProvenanceTracker()
        pass_inst = JavaConstantPropagationPass()
        res = pass_inst.run(unit, tracker=tracker)
        src = JavaPrinter.print_code(res)

        self.assertIn('System.out.println("SECRET_123");', src)
        self.assertGreater(len(tracker.records), 0)

    def test_constant_propagation_protects_reassignments(self) -> None:
        source = """
        public class Safe {
            public void test() {
                int x = 1;
                x = 2;
                System.out.println(x);
            }
        }
        """
        unit = JavaParser(source).parse()
        tracker = ProvenanceTracker()
        pass_inst = JavaConstantPropagationPass()
        res = pass_inst.run(unit, tracker=tracker)
        src = JavaPrinter.print_code(res)
        self.assertIn("System.out.println(x);", src)

    def test_expression_folding_arithmetic_and_strings(self) -> None:
        source = """
        public class MathFold {
            public static final int V1 = 10 * 5 + 4;
            public static final int V2 = 0xFF & 0x0F;
            public static final int V3 = 1 << 4;
            public static final boolean B1 = true && false;
            public static final boolean B2 = !false;
            public static final String S1 = "hello " + "world";
        }
        """
        unit = JavaParser(source).parse()
        tracker = ProvenanceTracker()
        pass_inst = JavaExpressionFoldingPass()
        res = pass_inst.run(unit, tracker=tracker)
        src = JavaPrinter.print_code(res)

        self.assertIn("int V1 = 54;", src)
        self.assertIn("int V2 = 15;", src)
        self.assertIn("int V3 = 16;", src)
        self.assertIn("boolean B1 = false;", src)
        self.assertIn("boolean B2 = true;", src)
        self.assertIn('String S1 = "hello world";', src)

    def test_decoder_detection_base64_and_radix(self) -> None:
        source = """
        import java.util.Base64;

        public class DecoderTest {
            public void run() {
                String s1 = new String(Base64.getDecoder().decode("SGVsbG8gSmF2YSE="));
                int p1 = Integer.parseInt("1F90", 16);
                int p2 = Integer.valueOf("42");
                String upper = "test".toUpperCase();
            }
        }
        """
        unit = JavaParser(source).parse()
        tracker = ProvenanceTracker()
        pass_inst = JavaDecoderDetectionPass()
        res = pass_inst.run(unit, tracker=tracker)
        src = JavaPrinter.print_code(res)

        self.assertIn('String s1 = "Hello Java!";', src)
        self.assertIn("int p1 = 8080;", src)
        self.assertIn("int p2 = 42;", src)
        self.assertIn('String upper = "TEST";', src)

    def test_string_reconstruction(self) -> None:
        source = """
        public class StringRecon {
            public void run() {
                String s1 = new String(new byte[] { 74, 97, 118, 97 });
                String s2 = new String(new char[] { 'O', 'K' });
                String s3 = new StringBuilder().append("alpha").append("-").append("beta").toString();
            }
        }
        """
        unit = JavaParser(source).parse()
        tracker = ProvenanceTracker()
        pass_inst = JavaStringReconstructionPass()
        res = pass_inst.run(unit, tracker=tracker)
        src = JavaPrinter.print_code(res)

        self.assertIn('String s1 = "Java";', src)
        self.assertIn('String s2 = "OK";', src)
        self.assertIn('String s3 = "alpha-beta";', src)

    def test_dead_code_elimination(self) -> None:
        source = """
        public class DeadCodeTest {
            public int test() {
                if (false) {
                    System.out.println("unreachable");
                }
                if (true) {
                    int a = 1;
                } else {
                    int b = 2;
                }
                return 42;
                int c = 3;
            }
        }
        """
        unit = JavaParser(source).parse()
        tracker = ProvenanceTracker()
        pass_inst = JavaDeadCodePass()
        res = pass_inst.run(unit, tracker=tracker)
        src = JavaPrinter.print_code(res)

        self.assertNotIn("unreachable", src)
        self.assertNotIn("int b = 2;", src)
        self.assertNotIn("int c = 3;", src)
        self.assertIn("return 42;", src)

    def test_full_pipeline_convergence_and_audit_report(self) -> None:
        source = """
        package com.example.obfuscated;

        import java.util.Base64;

        public class SecurityCheck {
            public static final String TOKEN_B64 = "U3VwZXJTZWNyZXQ=";
            public static final int OFFSET = 5 * 2;

            public static void verify() {
                String token = new String(Base64.getDecoder().decode(TOKEN_B64));
                String tag = new StringBuilder().append("tag-").append("v1").toString();
                int port = Integer.parseInt("22B8", 16);

                if (false) {
                    System.exit(1);
                }

                System.out.println(token);
                System.out.println(tag);
                System.out.println(OFFSET);
                System.out.println(port);
            }
        }
        """
        unit = JavaParser(source).parse()
        pipeline = Pipeline(min_confidence=ConfidenceLevel.LOW)
        pipeline.add_pass(JavaConstantPropagationPass())
        pipeline.add_pass(JavaExpressionFoldingPass())
        pipeline.add_pass(JavaDecoderDetectionPass())
        pipeline.add_pass(JavaStringReconstructionPass())
        pipeline.add_pass(JavaDeadCodePass())

        result = pipeline.execute(unit, max_iterations=5, until_convergence=True)
        final_code = JavaPrinter.print_code(result)

        self.assertIn('"SuperSecret"', final_code)
        self.assertIn('"tag-v1"', final_code)
        self.assertIn("int OFFSET = 10;", final_code)
        self.assertIn("int port = 8888;", final_code)
        self.assertNotIn("System.exit(1);", final_code)

        report = pipeline.generate_report()
        self.assertIn("Universal Deobfuscator Audit Report", report)
        self.assertGreater(pipeline.tracker.get_engine().compute_average_confidence(), 0.9)


if __name__ == "__main__":
    unittest.main()
