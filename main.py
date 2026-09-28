#!/usr/bin/env python3
"""UNMASK: Universal Code Deobfuscator & Reverse Engineering Engine.

Copyright (C) 2026 Sayantan. All rights reserved.
Licensed under the GNU General Public License v3.0 (GPLv3).
See LICENSE file in project root for full license details.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from core.confidence import ConfidenceLevel
from core.exceptions import DeobfuscatorError, ParseError, UnsupportedLanguageError
from core.pipeline import Pipeline
from languages import registry
import languages.python  # Ensure Python language is registered
import languages.javascript  # Ensure JavaScript language is registered
import languages.typescript  # Ensure TypeScript language is registered
import languages.java  # Ensure Java and Java Bytecode languages are registered
import languages.go  # Ensure Go language is registered

# Enable ANSI virtual terminal colors on Windows 10/11 console
if sys.platform == "win32":
    try:
        import os
        os.system("")
    except Exception:
        pass


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure structured logging based on verbosity flags."""
    if debug:
        level = logging.DEBUG
        fmt = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    elif verbose:
        level = logging.INFO
        fmt = "[%(levelname)s] %(message)s"
    else:
        level = logging.WARNING
        fmt = "%(message)s"

    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)


def detect_command(args: argparse.Namespace) -> int:
    """Detect language of the provided file."""
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: File '{args.input}' not found.", file=sys.stderr)
        return 1

    lang = registry.detect_language(input_path.name)
    if lang:
        print(f"File: {args.input}")
        print(f"Language: {lang.name}")
        return 0
    else:
        print(f"Could not automatically detect language for '{args.input}'.", file=sys.stderr)
        print(f"Supported languages: {', '.join(registry.supported_languages)}", file=sys.stderr)
        return 1


def read_source_file(input_path: Path) -> str:
    """Read a source file securely, with automatic fallback for non-UTF8/latin-1 encodings."""
    try:
        return input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return input_path.read_text(encoding="latin-1")
        except Exception as e:
            raise ParseError(f"Failed to read file '{input_path}' due to encoding error: {e}") from e
    except Exception as e:
        raise DeobfuscatorError(f"Failed to read file '{input_path}': {e}") from e


def parse_command(args: argparse.Namespace) -> int:
    """Parse input file and display syntax validity and regenerated source."""
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: File '{args.input}' not found.", file=sys.stderr)
        return 1

    lang_name = args.language or (registry.detect_language(input_path.name).name if registry.detect_language(input_path.name) else None)
    if not lang_name:
        print(f"Error: Please specify --language for '{args.input}'.", file=sys.stderr)
        return 1

    try:
        lang = registry.get(lang_name)
    except UnsupportedLanguageError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if input_path.suffix.lower() in (".class", ".jar"):
        source = ""
    else:
        try:
            source = read_source_file(input_path)
        except DeobfuscatorError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    try:
        tree = lang.parse(source, filename=str(input_path))
        print(f"Successfully parsed '{args.input}' as {lang.name}.")
        if args.show_ast:
            print("\n--- AST Dump ---")
            import ast
            if isinstance(tree, ast.AST):
                print(ast.dump(tree, indent=2))
            else:
                import pprint
                print(pprint.pformat(tree, indent=2, width=80))
        if args.unparse:
            if lang.name == "typescript" and getattr(args, "target_js", False):
                regenerated = lang.unparse(tree, target_js=True)
            else:
                regenerated = lang.unparse(tree)
            if getattr(args, "output", None):
                out_path = Path(args.output).expanduser()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(regenerated, encoding="utf-8")
                print(f"Regenerated source written to '{args.output}'.")
            else:
                print("\n--- Regenerated Source ---")
                print(regenerated)
        return 0
    except ParseError as e:
        print(f"Syntax Error in '{args.input}':\n  {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if args.debug:
            raise
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 3


def deobfuscate_command(args: argparse.Namespace) -> int:
    """Execute the deobfuscation pipeline on the target file."""
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: File '{args.input}' not found.", file=sys.stderr)
        return 1

    lang_name = args.language or (registry.detect_language(input_path.name).name if registry.detect_language(input_path.name) else None)
    if not lang_name:
        print(f"Error: Please specify --language for '{args.input}'.", file=sys.stderr)
        return 1

    try:
        lang = registry.get(lang_name)
    except UnsupportedLanguageError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        min_conf = ConfidenceLevel.from_str(getattr(args, "min_confidence", "LOW"))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if input_path.suffix.lower() in (".class", ".jar"):
        source = ""
    else:
        try:
            source = read_source_file(input_path)
        except DeobfuscatorError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    try:
        tree = lang.parse(source, filename=str(input_path))

        if getattr(args, "use_ir", False):
            from core.ir_pipeline import IRPipeline
            ir_mod = lang.to_ir(tree)
            ir_pipeline = IRPipeline(min_confidence=min_conf)
            ir_mod = ir_pipeline.execute(ir_mod, max_iterations=args.max_iterations)
            recovered_ast = lang.from_ir(ir_mod)
            if lang.name == "typescript" and getattr(args, "target_js", False):
                output_code = lang.unparse(recovered_ast, target_js=True)
            else:
                output_code = lang.unparse(recovered_ast)
            if args.output:
                out_path = Path(args.output).expanduser()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(output_code, encoding="utf-8")
                print(f"Deobfuscated (via IR) written to {args.output}")
            else:
                print(output_code)
            if getattr(args, "confidence", False):
                engine = ir_pipeline.tracker.get_engine()
                print(f"\nAverage Confidence Score: {engine.compute_average_confidence():.2f}")
            if getattr(args, "report", False):
                report_fmt = getattr(args, "format", "text")
                print("\n" + ir_pipeline.generate_report(format_type=report_fmt))
            return 0

        pipeline = Pipeline(min_confidence=min_conf)
        
        # Phase 1, Phase 2, Phase 3, and Phase 4 passes for Python
        if lang.name == "python":
            from passes.import_analysis import ImportNormalizationPass
            from passes.function_inlining import FunctionInliningPass
            from passes.constant_propagation import ConstantPropagationPass
            from passes.cff_recovery import ControlFlowFlatteningPass
            from passes.decoder_detection import DecoderDetectionPass
            from passes.string_reconstruction import StringReconstructionPass
            from passes.symbolic_evaluation import SymbolicEvaluationPass
            from passes.expression_folding import ExpressionFoldingPass
            from passes.simplify import SimplificationPass
            from passes.cfg_reduction import CFGReductionPass
            from passes.dead_code import DeadCodeEliminationPass
            from passes.type_annotation import TypeAnnotationPass

            pipeline.add_pass(ImportNormalizationPass(filename=str(input_path)))
            pipeline.add_pass(FunctionInliningPass(filename=str(input_path)))
            pipeline.add_pass(ConstantPropagationPass(filename=str(input_path)))
            pipeline.add_pass(ControlFlowFlatteningPass(filename=str(input_path)))
            pipeline.add_pass(DecoderDetectionPass(filename=str(input_path)))
            pipeline.add_pass(StringReconstructionPass(filename=str(input_path)))
            pipeline.add_pass(SymbolicEvaluationPass(filename=str(input_path)))
            pipeline.add_pass(ExpressionFoldingPass(filename=str(input_path)))
            pipeline.add_pass(SimplificationPass(filename=str(input_path)))
            pipeline.add_pass(CFGReductionPass(filename=str(input_path)))
            pipeline.add_pass(DeadCodeEliminationPass(filename=str(input_path)))
            pipeline.add_pass(TypeAnnotationPass(filename=str(input_path)))

            if getattr(args, "dynamic", False):
                from dynamic.unmasker import DynamicDecoderUnmasker
                pipeline.add_pass(DynamicDecoderUnmasker())

        elif lang.name in ("javascript", "typescript"):
            from languages.javascript.passes import (
                JSConstantPropagationPass,
                JSExpressionFoldingPass,
                JSDecoderDetectionPass,
                JSStringReconstructionPass,
                JSPropertyNormalizationPass,
                JSIIFENormalizationPass,
            )

            pipeline.add_pass(JSConstantPropagationPass(filename=str(input_path)))
            pipeline.add_pass(JSDecoderDetectionPass(filename=str(input_path)))
            pipeline.add_pass(JSStringReconstructionPass(filename=str(input_path)))
            pipeline.add_pass(JSExpressionFoldingPass(filename=str(input_path)))
            pipeline.add_pass(JSPropertyNormalizationPass(filename=str(input_path)))
            pipeline.add_pass(JSIIFENormalizationPass(filename=str(input_path)))

        elif lang.name in ("java", "java-bytecode"):
            from languages.java.passes import (
                JavaConstantPropagationPass,
                JavaExpressionFoldingPass,
                JavaDecoderDetectionPass,
                JavaStringReconstructionPass,
                JavaDeadCodePass,
            )

            pipeline.add_pass(JavaConstantPropagationPass(filename=str(input_path)))
            pipeline.add_pass(JavaExpressionFoldingPass(filename=str(input_path)))
            pipeline.add_pass(JavaDecoderDetectionPass(filename=str(input_path)))
            pipeline.add_pass(JavaStringReconstructionPass(filename=str(input_path)))
            pipeline.add_pass(JavaDeadCodePass(filename=str(input_path)))

        elif lang.name == "go":
            from languages.go.passes import (
                GoConstantPropagationPass,
                GoExpressionFoldingPass,
                GoDecoderDetectionPass,
                GoStringReconstructionPass,
                GoDeadCodePass,
            )

            pipeline.add_pass(GoConstantPropagationPass(filename=str(input_path)))
            pipeline.add_pass(GoExpressionFoldingPass(filename=str(input_path)))
            pipeline.add_pass(GoDecoderDetectionPass(filename=str(input_path)))
            pipeline.add_pass(GoStringReconstructionPass(filename=str(input_path)))
            pipeline.add_pass(GoDeadCodePass(filename=str(input_path)))

        result = pipeline.execute(tree, max_iterations=getattr(args, "max_iterations", 10), until_convergence=True)
        if lang.name == "typescript" and getattr(args, "target_js", False):
            output_code = lang.unparse(result, target_js=True)
        else:
            output_code = lang.unparse(result)

        if args.output:
            out_path = Path(args.output).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_code, encoding="utf-8")
            print(f"Deobfuscated output written to '{args.output}'.")
        else:
            print(output_code)

        if args.confidence:
            engine = pipeline.tracker.get_engine()
            print(f"\nAverage Confidence Score: {engine.compute_average_confidence():.2f}")
            print("Confidence Breakdown:")
            for lvl, cnt in engine.level_breakdown.items():
                if cnt > 0:
                    print(f"  [{lvl}]: {cnt}")
            print("Category Breakdown:")
            for cat, cnt in engine.category_breakdown.items():
                if cnt > 0:
                    print(f"  {cat}: {cnt}")

        if args.report:
            report_fmt = getattr(args, "format", "text")
            print("\n" + pipeline.generate_report(format_type=report_fmt))

        if args.confidence or args.report:
            dynamic_active = getattr(args, "dynamic", False)
            dynamic_unmasked = sum(1 for rec in pipeline.tracker.records if rec.pass_name == "DynamicDecoderUnmasker")
            print("\nDynamic execution:")
            if dynamic_active:
                print("  Performed: Yes (Isolated sandbox, timeout=2.0s, max_memory=64MB)")
                print(f"  Decoders unmasked: {dynamic_unmasked}")
            else:
                print("  Not performed")

        return 0
    except ParseError as e:
        print(f"Cannot deobfuscate due to syntax error:\n  {e}", file=sys.stderr)
        return 2
    except DeobfuscatorError as e:
        print(f"Deobfuscation failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        if args.debug:
            raise
        print(f"Unexpected failure: {e}", file=sys.stderr)
        return 3


def analyze_command(args: argparse.Namespace) -> int:
    """Analyze input file and display structure, metrics, and detected obfuscation patterns."""
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: File '{args.input}' not found.", file=sys.stderr)
        return 1

    lang_name = args.language or (registry.detect_language(input_path.name).name if registry.detect_language(input_path.name) else None)
    if not lang_name:
        print(f"Error: Please specify --language for '{args.input}'.", file=sys.stderr)
        return 1

    try:
        lang = registry.get(lang_name)
    except UnsupportedLanguageError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if input_path.suffix.lower() in (".class", ".jar"):
        source = ""
    else:
        try:
            source = read_source_file(input_path)
        except DeobfuscatorError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        tree = lang.parse(source, filename=str(input_path))
        lines = [
            f"File: {args.input}",
            f"Language: {lang.name}",
            "Status: Syntax valid",
        ]

        from core.provenance import ProvenanceTracker
        tracker = ProvenanceTracker()
        patterns = []

        if lang.name == "python":
            import ast
            from passes.decoder_detection import DecoderDetectionPass
            from passes.cff_recovery import ControlFlowFlatteningPass

            node_count = sum(1 for _ in ast.walk(tree))
            lines.append(f"AST Nodes: {node_count}")

            dec_pass = DecoderDetectionPass(filename=str(input_path))
            dec_pass.run(tree, tracker)
            cff_pass = ControlFlowFlatteningPass(filename=str(input_path))
            cff_pass.run(tree, tracker)

            dec_count = sum(1 for r in tracker.records if r.pass_name == "DecoderDetection")
            if dec_count:
                patterns.append(f"Decoders ({dec_count} detected)")
            cff_count = sum(1 for r in tracker.records if r.pass_name == "ControlFlowFlattening")
            if cff_count:
                patterns.append(f"Control Flow Flattening ({cff_count} loops)")

        elif lang.name in ("javascript", "typescript"):
            from languages.javascript.passes import JSDecoderDetectionPass
            dec_pass = JSDecoderDetectionPass(filename=str(input_path))
            dec_pass.run(tree, tracker)
            dec_count = len(tracker.records)
            if dec_count:
                patterns.append(f"Decoders ({dec_count} detected)")

        elif lang.name in ("java", "java-bytecode"):
            from languages.java.passes import JavaDecoderDetectionPass
            dec_pass = JavaDecoderDetectionPass(filename=str(input_path))
            dec_pass.run(tree, tracker)
            dec_count = len(tracker.records)
            if dec_count:
                patterns.append(f"Decoders ({dec_count} detected)")

        elif lang.name == "go":
            from languages.go.passes import GoDecoderDetectionPass
            dec_pass = GoDecoderDetectionPass(filename=str(input_path))
            dec_pass.run(tree, tracker)
            dec_count = len(tracker.records)
            if dec_count:
                patterns.append(f"Decoders ({dec_count} detected)")

        if patterns:
            lines.append(f"Detected Obfuscation Patterns: {', '.join(patterns)}")
        else:
            lines.append("Detected Obfuscation Patterns: None detected via static heuristics")

        report_text = "\n".join(lines)
        if getattr(args, "output", None):
            out_p = Path(args.output).expanduser()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(report_text, encoding="utf-8")
            print(f"Analysis written to '{args.output}'.")
        else:
            print(report_text)

        return 0
    except ParseError as e:
        print(f"Syntax error in '{args.input}':\n  {e}", file=sys.stderr)
        return 2
    except Exception as e:
        if args.debug:
            raise
        print(f"Analysis failed: {e}", file=sys.stderr)
        return 3


def report_command(args: argparse.Namespace) -> int:
    """Run deobfuscation analysis and generate an audit report."""
    setattr(args, "report", True)
    setattr(args, "output", getattr(args, "output", None))
    if not hasattr(args, "target_js"):
        setattr(args, "target_js", False)
    if not hasattr(args, "confidence"):
        setattr(args, "confidence", True)
    if not hasattr(args, "min_confidence"):
        setattr(args, "min_confidence", "LOW")
    if not hasattr(args, "max_iterations"):
        setattr(args, "max_iterations", 10)
    if not hasattr(args, "dynamic"):
        setattr(args, "dynamic", False)
    return deobfuscate_command(args)


def ir_command(args: argparse.Namespace) -> int:
    """Translate source file to Common IR, perform IR-level optimization, or view CFG."""
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        print(f"Error: File '{args.input}' not found.", file=sys.stderr)
        return 1

    lang_name = args.language or (registry.detect_language(input_path.name).name if registry.detect_language(input_path.name) else None)
    if not lang_name:
        print(f"Error: Please specify --language for '{args.input}'.", file=sys.stderr)
        return 1

    try:
        lang = registry.get(lang_name)
    except UnsupportedLanguageError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if input_path.suffix.lower() in (".class", ".jar"):
        source = ""
    else:
        try:
            source = read_source_file(input_path)
        except DeobfuscatorError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        tree = lang.parse(source, filename=str(input_path))
        ir_mod = lang.to_ir(tree)

        from core.ir_pipeline import IRPipeline
        pipeline = IRPipeline()

        if getattr(args, "optimize", False):
            ir_mod = pipeline.execute(ir_mod, max_iterations=getattr(args, "max_iterations", 5))

        if getattr(args, "cfg", False):
            cfgs = pipeline.build_cfgs(ir_mod)
            for name, cfg in cfgs.items():
                print(cfg.to_ascii())
            return 0

        if getattr(args, "roundtrip", False):
            recovered = lang.from_ir(ir_mod)
            if lang.name == "typescript" and getattr(args, "target_js", False):
                out_code = lang.unparse(recovered, target_js=True)
            else:
                out_code = lang.unparse(recovered)
            if args.output:
                out_p = Path(args.output).expanduser()
                out_p.parent.mkdir(parents=True, exist_ok=True)
                out_p.write_text(out_code, encoding="utf-8")
                print(f"Roundtripped source written to {args.output}")
            else:
                print(out_code)
            return 0

        ir_dump = pipeline.dump(ir_mod)
        if args.output:
            out_p = Path(args.output).expanduser()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(ir_dump, encoding="utf-8")
            print(f"IR written to {args.output}")
        else:
            print(ir_dump)

        if getattr(args, "report", False):
            print("\n--- Provenance Audit Report ---")
            print(pipeline.generate_report(getattr(args, "format", "text")))

        return 0
    except Exception as e:
        if args.debug:
            raise
        print(f"IR processing failed: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for CLI commands."""
    parser = argparse.ArgumentParser(
        prog="unmask",
        description="UNMASK: Universal Deobfuscator & code reverse engineering framework.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode and full tracebacks")
    parser.add_argument("-b", "--banner", "--matrix", action="store_true", help="Display the UNMASK Matrix banner and exit")
    parser.add_argument("-m", "--menu", action="store_true", help="Launch interactive console menu mode")
    parser.add_argument("--no-rain", action="store_true", help="Skip the matrix digital rain animation")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # detect
    detect_parser = subparsers.add_parser("detect", help="Detect the programming language of a file")
    detect_parser.add_argument("input", help="Path to input source file")

    # parse
    parse_parser = subparsers.add_parser("parse", help="Parse and validate source file syntax")
    parse_parser.add_argument("input", help="Path to input source file")
    parse_parser.add_argument("-o", "--output", help="Write regenerated source to specified file")
    parse_parser.add_argument("-l", "--language", help="Explicit language override")
    parse_parser.add_argument("--show-ast", action="store_true", help="Display AST representation")
    parse_parser.add_argument("--unparse", action="store_true", help="Display regenerated source code")
    parse_parser.add_argument(
        "--target-js",
        action="store_true",
        help="Compile/unparse TypeScript to clean JavaScript (strip types)",
    )

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze code structure and detect obfuscation patterns")
    analyze_parser.add_argument("input", help="Path to input source file")
    analyze_parser.add_argument("-o", "--output", help="Write analysis report to specified file")
    analyze_parser.add_argument("-l", "--language", help="Explicit language override")

    # report
    report_parser = subparsers.add_parser("report", help="Generate deobfuscation audit and provenance report")
    report_parser.add_argument("input", help="Path to input source file")
    report_parser.add_argument("-o", "--output", help="Write output to specified file")
    report_parser.add_argument("-l", "--language", help="Explicit language override")
    report_parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Audit report output format (default: text)",
    )
    report_parser.add_argument("--use-ir", action="store_true", help="Analyze using Common IR pipeline")
    report_parser.add_argument(
        "--min-confidence",
        default="LOW",
        help="Minimum confidence threshold required (CERTAIN, HIGH, MEDIUM, LOW, UNKNOWN, default: LOW)",
    )
    report_parser.add_argument(
        "--confidence",
        action="store_true",
        default=True,
        help="Display summary confidence score and metrics",
    )
    report_parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum deobfuscation pass iterations (default: 10)",
    )
    report_parser.add_argument(
        "--dynamic",
        action="store_true",
        default=False,
        help="Enable opt-in secure dynamic analysis in isolated sandbox",
    )

    # deobfuscate
    deob_parser = subparsers.add_parser("deobfuscate", help="Deobfuscate source file")
    deob_parser.add_argument("input", help="Path to input source file")
    deob_parser.add_argument("-o", "--output", help="Write output to specified file")
    deob_parser.add_argument("-l", "--language", help="Explicit language override")
    deob_parser.add_argument(
        "--target-js",
        action="store_true",
        help="Compile/unparse TypeScript to clean JavaScript (strip types)",
    )
    deob_parser.add_argument("--use-ir", action="store_true", help="Deobfuscate using Common IR pipeline")
    deob_parser.add_argument("--report", action="store_true", help="Print audit report")
    deob_parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Audit report output format (default: text)",
    )
    deob_parser.add_argument(
        "--min-confidence",
        default="LOW",
        help="Minimum confidence threshold required (CERTAIN, HIGH, MEDIUM, LOW, UNKNOWN, default: LOW)",
    )
    deob_parser.add_argument(
        "--confidence",
        action="store_true",
        help="Display summary confidence score and metrics",
    )
    deob_parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum deobfuscation pass iterations (default: 10)",
    )
    deob_parser.add_argument(
        "--dynamic",
        action="store_true",
        default=False,
        help="Enable opt-in secure dynamic analysis in isolated sandbox",
    )
    deob_parser.add_argument(
        "--no-dynamic",
        action="store_false",
        dest="dynamic",
        help="Disable dynamic analysis (default)",
    )

    # ir
    ir_parser = subparsers.add_parser("ir", help="Common Intermediate Representation (IR) tools")
    ir_parser.add_argument("input", help="Path to input source file")
    ir_parser.add_argument("-o", "--output", help="Write output to specified file")
    ir_parser.add_argument("-l", "--language", help="Explicit language override")
    ir_parser.add_argument("-O", "--optimize", action="store_true", help="Run universal IR optimization passes")
    ir_parser.add_argument("--cfg", action="store_true", help="Display ASCII Control Flow Graph of the IR")
    ir_parser.add_argument("--roundtrip", action="store_true", help="Convert IR back to source and unparse")
    ir_parser.add_argument(
        "--target-js",
        action="store_true",
        help="Compile/unparse TypeScript to clean JavaScript (strip types)",
    )
    ir_parser.add_argument("--report", action="store_true", help="Print audit report")
    ir_parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Audit report output format (default: text)",
    )
    ir_parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum IR optimization pass iterations (default: 5)",
    )

    # interactive / menu
    subparsers.add_parser("interactive", help="Start interactive console menu")
    subparsers.add_parser("menu", help="Start interactive console menu (alias)")

    return parser


def print_banner(skip_rain: bool = True) -> None:
    """Display the UNMASK ASCII banner and developer attribution."""
    use_color = sys.stdout.isatty()
    g_hi = "\033[1;92m" if use_color else ""       # Bright phosphor green
    g_mid = "\033[32m" if use_color else ""        # Standard matrix green
    g_dim = "\033[2;32m" if use_color else ""      # Dim/dark matrix green
    c_white = "\033[1;97m" if use_color else ""    # Bright white highlight
    c_cyan = "\033[96m" if use_color else ""       # Bright cyan
    c_bold = "\033[1m" if use_color else ""
    c_reset = "\033[0m" if use_color else ""

    banner = f"""{g_hi}
           ██╗   ██╗███╗   ██╗███╗   ███╗ █████╗ ███████╗██╗  ██╗
           ██║   ██║████╗  ██║████╗ ████║██╔══██╗██╔════╝██║ ██╔╝
           ██║   ██║██╔██╗ ██║██╔████╔██║███████║███████╗█████╔╝ 
           ██║   ██║██║╚██╗██║██║╚██╔╝██║██╔══██║╚════██║██╔═██╗ 
           ╚██████╔╝██║ ╚████║██║ ╚═╝ ██║██║  ██║███████║██║  ██╗
            ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝{c_reset}
{g_dim}  ────────────────────────────────────────────────────────────────────────{c_reset}
{c_white}      UNMASK :: Universal Code Deobfuscator & Reverse Engineering Tool{c_reset}
{c_cyan}                        [ DEVELOPED BY : SAYANTAN ]{c_reset}
{g_dim}  ────────────────────────────────────────────────────────────────────────{c_reset}
  {g_dim}::{c_reset} {c_bold}Target Languages{c_reset} : {g_mid}Python 3.11+ │ JavaScript │ TypeScript │ Java │ Go{c_reset}
  {g_dim}::{c_reset} {c_bold}Core Subsystems {c_reset} : {g_mid}AST Transforms │ CFG De-Flattening │ Opaque Pruner{c_reset}
  {g_dim}::{c_reset} {c_bold}Decoders & Crypto{c_reset}: {g_mid}Base64 │ Hex │ URL │ XOR │ Zlib │ Unicode Unpack{c_reset}
  {g_dim}::{c_reset} {c_bold}Dynamic Sandbox {c_reset} : {g_mid}Subprocess POSIX Jail │ CPU & RAM Limits │ Tracing{c_reset}
{g_dim}  ────────────────────────────────────────────────────────────────────────{c_reset}"""
    print(banner)


def interactive_menu() -> int:
    """Interactive console menu for UNMASK."""
    print_banner()

    use_color = sys.stdout.isatty()
    c_green = "\033[92m" if use_color else ""
    c_cyan = "\033[96m" if use_color else ""
    c_bold = "\033[1m" if use_color else ""
    c_dim = "\033[2m" if use_color else ""
    c_reset = "\033[0m" if use_color else ""

    op_names = {
        "1": "Deobfuscate Payload",
        "2": "Static Analysis",
        "3": "Syntax & AST Dump",
        "4": "Common IR Tools",
        "5": "Detect Language",
    }

    while True:
        print(f"\n{c_bold}{c_green}[ CORE OPERATIONS ]{c_reset}")
        print(f"  {c_cyan}[1]{c_reset} ⚡ {c_bold}Deobfuscate Payload{c_reset}      (Unpack, decode strings, simplify logic)")
        print(f"  {c_cyan}[2]{c_reset} 🔍 {c_bold}Static Analysis{c_reset}          (Inspect obfuscation patterns & metrics)")
        print(f"  {c_cyan}[3]{c_reset} ⚙️  {c_bold}Syntax & AST Dump{c_reset}        (Validate grammar, view AST / clean code)")
        print(f"  {c_cyan}[4]{c_reset} 🛠️  {c_bold}Common IR Tools{c_reset}          (Universal IR optimization / CFG graph)")
        print(f"  {c_cyan}[5]{c_reset} 🏷️  {c_bold}Detect Language{c_reset}          (Analyze file signatures & headers)")
        print(f"  {c_cyan}[6]{c_reset} ❌ {c_bold}Terminate Session{c_reset}\n")

        try:
            choice = input(f"{c_bold}{c_green}unmask{c_reset}@{c_cyan}engine{c_reset}:{c_dim}~#{c_reset} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Session terminated.")
            return 0

        if choice in ("6", "0", "q", "quit", "exit"):
            print("\n[*] Exiting UNMASK. Goodbye!")
            return 0

        if choice not in op_names:
            print("[!] Invalid option. Please enter a number between 1 and 6.")
            continue

        op_name = op_names[choice]
        print(f"\n{c_bold}{c_cyan}[*] Selected Operation [{choice}]: {op_name}{c_reset}")
        print(f"  {c_cyan}[1]{c_reset} Proceed with operation on target file")
        print(f"  {c_cyan}[2]{c_reset} 🔄 Revert file changes (Restore from .unmask.bak backup)")
        print(f"  {c_cyan}[0]{c_reset} ↩️  Change operation / Return to main menu\n")

        try:
            action = input(f"{c_bold}[?] Enter choice [1/2/0, default: 1] or file path:{c_reset} ").strip()
            if (action.startswith('"') and action.endswith('"')) or (action.startswith("'") and action.endswith("'")):
                action = action[1:-1]
        except (KeyboardInterrupt, EOFError):
            continue

        if action in ("0", "b", "back", "cancel", "q"):
            print(f"{c_dim}[*] Operation changed. Returning to main menu...{c_reset}")
            continue

        if action in ("2", "r", "revert"):
            try:
                rev_path = input(f"{c_bold}[?] Path of file to revert:{c_reset} ").strip()
                if (rev_path.startswith('"') and rev_path.endswith('"')) or (rev_path.startswith("'") and rev_path.endswith("'")):
                    rev_path = rev_path[1:-1]
            except (KeyboardInterrupt, EOFError):
                continue
            if not rev_path:
                print("[!] Error: No file path provided.")
                continue
            bak_path = Path(f"{rev_path}.unmask.bak")
            target_p = Path(rev_path)
            if bak_path.exists():
                import shutil
                shutil.copy2(bak_path, target_p)
                print(f"{c_bold}{c_green}[+] Successfully reverted '{target_p.name}' from '{bak_path.name}'.{c_reset}")
                print(f"{c_dim}[*] Original contents restored.{c_reset}")
            else:
                print(f"[!] No backup file '{bak_path.name}' found for '{target_p.name}'.")
                print(f"    (If the file was not overwritten, its original state is already preserved.)")
            continue

        if action in ("1", ""):
            try:
                raw_path = input(f"{c_bold}[?] Target file path (or '0' to change operation):{c_reset} ").strip()
                if (raw_path.startswith('"') and raw_path.endswith('"')) or (raw_path.startswith("'") and raw_path.endswith("'")):
                    raw_path = raw_path[1:-1]
            except (KeyboardInterrupt, EOFError):
                continue
            if raw_path in ("0", "b", "back", "cancel", "q"):
                print(f"{c_dim}[*] Operation cancelled. Returning to main menu...{c_reset}")
                continue
        else:
            raw_path = action

        if not raw_path:
            print("[!] Error: No target file path provided.")
            continue

        if choice == "1":
            try:
                conf = input(f"{c_bold}[?] Display confidence score? [Y/n]:{c_reset} ").strip().lower() != "n"
                rep = input(f"{c_bold}[?] Display transformation audit report? [y/N]:{c_reset} ").strip().lower() == "y"
                dyn = input(f"{c_bold}[?] Enable isolated dynamic sandbox? [y/N]:{c_reset} ").strip().lower() == "y"
            except (KeyboardInterrupt, EOFError):
                continue

            cmd_args = ["deobfuscate", raw_path]
            if conf:
                cmd_args.append("--confidence")
            if rep:
                cmd_args.append("--report")
            if dyn:
                cmd_args.append("--dynamic")

            print(f"\n{c_bold}{c_cyan}[*] Executing multi-pass deobfuscation on: {raw_path}{c_reset}")
            main(cmd_args)
            print(f"\n{c_bold}{c_green}[+] Deobfuscation preview completed.{c_reset}")
            print(f"  {c_cyan}[1]{c_reset} 💾 Save clean output to a file")
            print(f"  {c_cyan}[2]{c_reset} 🔄 Revert / Discard changes (Keep original file untouched)")
            print(f"  {c_cyan}[3]{c_reset} ↩️  Change operation / Return to main menu\n")
            try:
                post_action = input(f"{c_bold}[?] Select action [1/2/3, default: 3]:{c_reset} ").strip()
            except (KeyboardInterrupt, EOFError):
                continue

            if post_action == "1":
                save_path = input(f"{c_bold}[?] Save output to file path (e.g. {raw_path}.clean.py):{c_reset} ").strip()
                if (save_path.startswith('"') and save_path.endswith('"')) or (save_path.startswith("'") and save_path.endswith("'")):
                    save_path = save_path[1:-1]
                if save_path:
                    if Path(save_path).resolve() == Path(raw_path).resolve():
                        bak = Path(f"{raw_path}.unmask.bak")
                        import shutil
                        shutil.copy2(raw_path, bak)
                        print(f"{c_dim}[*] Created backup '{bak.name}' before overwriting.{c_reset}")
                    main(["deobfuscate", raw_path, "-o", save_path])
                    print(f"{c_bold}{c_green}[+] Deobfuscated file written to '{save_path}'.{c_reset}")
            elif post_action == "2":
                bak = Path(f"{raw_path}.unmask.bak")
                if bak.exists():
                    import shutil
                    shutil.copy2(bak, raw_path)
                    print(f"{c_bold}{c_green}[+] Restored '{raw_path}' from backup.{c_reset}")
                else:
                    print(f"{c_bold}{c_cyan}[*] Changes discarded. Original file '{raw_path}' remains untouched.{c_reset}")
            else:
                print(f"{c_dim}[*] Returning to main menu.{c_reset}")

        elif choice == "2":
            print(f"\n{c_bold}{c_cyan}[*] Executing static analysis on: {raw_path}{c_reset}")
            main(["analyze", raw_path])
            print(f"\n{c_bold}{c_green}[+] Static analysis completed.{c_reset}")
            print(f"  {c_cyan}[1]{c_reset} 🔍 Analyze another file")
            print(f"  {c_cyan}[2]{c_reset} 🔄 Revert file from backup (.unmask.bak)")
            print(f"  {c_cyan}[3]{c_reset} ↩️  Change operation / Return to main menu\n")
            try:
                post = input(f"{c_bold}[?] Select action [1/2/3, default: 3]:{c_reset} ").strip()
            except (KeyboardInterrupt, EOFError):
                continue
            if post == "2":
                bak = Path(f"{raw_path}.unmask.bak")
                if bak.exists():
                    import shutil
                    shutil.copy2(bak, raw_path)
                    print(f"{c_bold}{c_green}[+] Restored '{raw_path}' from '{bak.name}'.{c_reset}")
                else:
                    print(f"{c_dim}[*] Original file '{raw_path}' is untouched. No backup found.{c_reset}")
            elif post == "1":
                pass
            else:
                print(f"{c_dim}[*] Returning to main menu.{c_reset}")

        elif choice == "3":
            try:
                show_ast = input(f"{c_bold}[?] Display full AST dump? [y/N]:{c_reset} ").strip().lower() == "y"
                unparse = input(f"{c_bold}[?] Display regenerated clean source? [Y/n]:{c_reset} ").strip().lower() != "n"
            except (KeyboardInterrupt, EOFError):
                continue

            cmd_args = ["parse", raw_path]
            if show_ast:
                cmd_args.append("--show-ast")
            if unparse:
                cmd_args.append("--unparse")

            print(f"\n{c_bold}{c_cyan}[*] Parsing and validating: {raw_path}{c_reset}")
            main(cmd_args)
            print(f"\n{c_bold}{c_green}[+] Syntax parsing completed.{c_reset}")
            print(f"  {c_cyan}[1]{c_reset} 💾 Save clean unparsed code to a file")
            print(f"  {c_cyan}[2]{c_reset} 🔄 Revert file from backup (.unmask.bak)")
            print(f"  {c_cyan}[3]{c_reset} ↩️  Change operation / Return to main menu\n")
            try:
                post = input(f"{c_bold}[?] Select action [1/2/3, default: 3]:{c_reset} ").strip()
            except (KeyboardInterrupt, EOFError):
                continue
            if post == "1":
                save_path = input(f"{c_bold}[?] Save output to file path:{c_reset} ").strip()
                if (save_path.startswith('"') and save_path.endswith('"')) or (save_path.startswith("'") and save_path.endswith("'")):
                    save_path = save_path[1:-1]
                if save_path:
                    if Path(save_path).resolve() == Path(raw_path).resolve():
                        bak = Path(f"{raw_path}.unmask.bak")
                        import shutil
                        shutil.copy2(raw_path, bak)
                        print(f"{c_dim}[*] Created backup '{bak.name}' before overwriting.{c_reset}")
                    main(["parse", raw_path, "--unparse", "-o", save_path])
                    print(f"{c_bold}{c_green}[+] Clean unparsed source written to '{save_path}'.{c_reset}")
            elif post == "2":
                bak = Path(f"{raw_path}.unmask.bak")
                if bak.exists():
                    import shutil
                    shutil.copy2(bak, raw_path)
                    print(f"{c_bold}{c_green}[+] Restored '{raw_path}' from '{bak.name}'.{c_reset}")
                else:
                    print(f"{c_dim}[*] Original file '{raw_path}' is untouched. No backup found.{c_reset}")
            else:
                print(f"{c_dim}[*] Returning to main menu.{c_reset}")

        elif choice == "4":
            print(f"\n{c_bold}{c_cyan}[*] Common IR Tools Submenu:{c_reset}")
            print("  [a] Optimize Common IR & dump")
            print("  [b] Render ASCII Control Flow Graph (CFG)")
            print("  [c] Roundtrip from Common IR back to source")
            print("  [0] ↩️  Change operation / Return to main menu\n")
            try:
                ir_opt = input(f"{c_bold}[?] Select IR operation [a/b/c/0, default: a]:{c_reset} ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                continue

            if ir_opt in ("0", "d", "back", "cancel", "q"):
                print(f"{c_dim}[*] Returning to main menu.{c_reset}")
                continue
            elif ir_opt == "b":
                main(["ir", raw_path, "--cfg"])
            elif ir_opt == "c":
                main(["ir", raw_path, "--roundtrip"])
            else:
                main(["ir", raw_path, "-O"])

            print(f"\n{c_bold}{c_green}[+] IR processing completed.{c_reset}")
            print(f"  {c_cyan}[1]{c_reset} 💾 Save IR / roundtrip output to file")
            print(f"  {c_cyan}[2]{c_reset} 🔄 Revert file from backup (.unmask.bak)")
            print(f"  {c_cyan}[3]{c_reset} ↩️  Change operation / Return to main menu\n")
            try:
                post = input(f"{c_bold}[?] Select action [1/2/3, default: 3]:{c_reset} ").strip()
            except (KeyboardInterrupt, EOFError):
                continue
            if post == "1":
                save_path = input(f"{c_bold}[?] Save output to file path:{c_reset} ").strip()
                if (save_path.startswith('"') and save_path.endswith('"')) or (save_path.startswith("'") and save_path.endswith("'")):
                    save_path = save_path[1:-1]
                if save_path:
                    if ir_opt == "c":
                        main(["ir", raw_path, "--roundtrip", "-o", save_path])
                    else:
                        main(["ir", raw_path, "-O", "-o", save_path])
                    print(f"{c_bold}{c_green}[+] IR output written to '{save_path}'.{c_reset}")
            elif post == "2":
                bak = Path(f"{raw_path}.unmask.bak")
                if bak.exists():
                    import shutil
                    shutil.copy2(bak, raw_path)
                    print(f"{c_bold}{c_green}[+] Restored '{raw_path}' from '{bak.name}'.{c_reset}")
                else:
                    print(f"{c_dim}[*] Original file '{raw_path}' is untouched. No backup found.{c_reset}")
            else:
                print(f"{c_dim}[*] Returning to main menu.{c_reset}")

        elif choice == "5":
            print(f"\n{c_bold}{c_cyan}[*] Scanning language signatures on: {raw_path}{c_reset}")
            main(["detect", raw_path])
            print(f"\n{c_bold}{c_green}[+] Detection completed.{c_reset}")
            print(f"  {c_cyan}[1]{c_reset} 🏷️  Detect another file")
            print(f"  {c_cyan}[2]{c_reset} ↩️  Change operation / Return to main menu\n")
            try:
                post = input(f"{c_bold}[?] Select action [1/2, default: 2]:{c_reset} ").strip()
            except (KeyboardInterrupt, EOFError):
                continue
            if post == "1":
                pass
            else:
                print(f"{c_dim}[*] Returning to main menu.{c_reset}")


def main(argv: Optional[list] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(verbose=args.verbose, debug=args.debug)

    if not args.command:
        if getattr(args, "banner", False):
            print_banner(skip_rain=getattr(args, "no_rain", False))
            return 0
        if getattr(args, "menu", False) or (argv is None and len(sys.argv) == 1 and sys.stdin.isatty()):
            return interactive_menu()
        parser.print_help()
        return 0

    if getattr(args, "banner", False):
        print_banner(skip_rain=getattr(args, "no_rain", False))

    if args.command in ("interactive", "menu") or getattr(args, "menu", False):
        return interactive_menu()
    elif args.command == "detect":
        return detect_command(args)
    elif args.command == "parse":
        return parse_command(args)
    elif args.command == "analyze":
        return analyze_command(args)
    elif args.command == "report":
        return report_command(args)
    elif args.command == "deobfuscate":
        return deobfuscate_command(args)
    elif args.command == "ir":
        return ir_command(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
