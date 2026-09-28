"""Decoder detection and transformation pass.

Phase 1D: Integrates decoder plugins into the AST transformation pipeline.
Detects and simplifies calls to standard decoding libraries when arguments are compile-time constants:
- base64.b64decode / urlsafe_b64decode / b64decode
- bytes.fromhex / binascii.unhexlify
- urllib.parse.unquote
- codecs.decode
- zlib.decompress / gzip.decompress
"""

import ast
from typing import Any, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from decoders import decoder_registry
from languages.python.parser import PythonParser
from passes.expression_folding import extract_constant_value, is_safe_constant


class DecoderDetectionTransformer(ast.NodeTransformer):
    """AST transformer that detects decoder invocations and simplifies them."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.num_decoded = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)

        # 1. base64.b64decode / b64decode
        if self._is_func(node.func, "b64decode", module="base64") or self._is_func(node.func, "standard_b64decode", module="base64"):
            if len(node.args) >= 1 and is_safe_constant(node.args[0]):
                val = extract_constant_value(node.args[0])
                b64_dec = decoder_registry.get("base64decoder")
                if b64_dec:
                    success, res, expl = b64_dec.decode(val)
                    if success:
                        return self._replace_constant(node, res, f"Evaluated base64.b64decode: {expl}")

        # 2. base64.urlsafe_b64decode / urlsafe_b64decode
        if self._is_func(node.func, "urlsafe_b64decode", module="base64"):
            if len(node.args) >= 1 and is_safe_constant(node.args[0]):
                val = extract_constant_value(node.args[0])
                b64_dec = decoder_registry.get("base64decoder")
                if b64_dec:
                    success, res, expl = b64_dec.decode(val)
                    if success:
                        return self._replace_constant(node, res, f"Evaluated base64.urlsafe_b64decode: {expl}")

        # 3. bytes.fromhex(arg)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "fromhex":
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "bytes":
                if len(node.args) >= 1 and is_safe_constant(node.args[0]):
                    val = extract_constant_value(node.args[0])
                    hex_dec = decoder_registry.get("hexdecoder")
                    if hex_dec:
                        success, res, expl = hex_dec.decode(val)
                        if success:
                            return self._replace_constant(node, res, f"Evaluated bytes.fromhex: {expl}")

        # 4. binascii.unhexlify / unhexlify / a2b_hex
        if self._is_func(node.func, "unhexlify", module="binascii") or self._is_func(node.func, "a2b_hex", module="binascii"):
            if len(node.args) >= 1 and is_safe_constant(node.args[0]):
                val = extract_constant_value(node.args[0])
                hex_dec = decoder_registry.get("hexdecoder")
                if hex_dec:
                    success, res, expl = hex_dec.decode(val)
                    if success:
                        return self._replace_constant(node, res, f"Evaluated binascii.unhexlify: {expl}")

        # 5. urllib.parse.unquote / unquote
        if self._is_func(node.func, "unquote", module="urllib.parse") or self._is_func(node.func, "unquote", module="parse"):
            if len(node.args) >= 1 and is_safe_constant(node.args[0]):
                val = extract_constant_value(node.args[0])
                url_dec = decoder_registry.get("urldecoder")
                if url_dec:
                    success, res, expl = url_dec.decode(val)
                    if success:
                        return self._replace_constant(node, res, f"Evaluated urllib.parse.unquote: {expl}")

        # 6. zlib.decompress
        if self._is_func(node.func, "decompress", module="zlib"):
            if len(node.args) >= 1 and is_safe_constant(node.args[0]):
                val = extract_constant_value(node.args[0])
                comp_dec = decoder_registry.get("compressiondecoder")
                if comp_dec:
                    success, res, expl = comp_dec.decode(val)
                    if success:
                        return self._replace_constant(node, res, f"Evaluated zlib.decompress: {expl}")

        # 7. codecs.decode(arg, encoding)
        if self._is_func(node.func, "decode", module="codecs"):
            if len(node.args) >= 2 and is_safe_constant(node.args[0]) and is_safe_constant(node.args[1]):
                val = extract_constant_value(node.args[0])
                encoding = str(extract_constant_value(node.args[1])).lower()
                if encoding in ("base64", "base_64", "b64"):
                    dec = decoder_registry.get("base64decoder")
                    if dec:
                        s, r, e = dec.decode(val)
                        if s:
                            return self._replace_constant(node, r, f"Evaluated codecs.decode({encoding}): {e}")
                elif encoding in ("hex", "hexlify", "unhexlify"):
                    dec = decoder_registry.get("hexdecoder")
                    if dec:
                        s, r, e = dec.decode(val)
                        if s:
                            return self._replace_constant(node, r, f"Evaluated codecs.decode({encoding}): {e}")
                elif encoding in ("rot13", "rot_13"):
                    import codecs
                    try:
                        res = codecs.decode(val, "rot_13")
                        return self._replace_constant(node, res, "Evaluated codecs.decode rot_13")
                    except Exception:
                        pass

        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        # Check standalone string literals for unicode escape patterns
        if isinstance(node.value, str):
            uni_dec = decoder_registry.get("unicodedecoder")
            if uni_dec and uni_dec.can_decode(node.value):
                success, res, expl = uni_dec.decode(node.value)
                if success:
                    return self._replace_constant(node, res, f"Decoded raw Unicode escapes: {expl}")
        return node

    def _is_func(self, node: ast.AST, name: str, module: Optional[str] = None) -> bool:
        """Check if AST node represents a specific function name, optionally inside a module."""
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            if module is None:
                return True
            # Check module: module.func or package.module.func
            if isinstance(node.value, ast.Name) and node.value.id == module.split(".")[-1]:
                return True
            if isinstance(node.value, ast.Attribute) and node.value.attr == module.split(".")[-1]:
                return True
        return False

    def _replace_constant(self, original_node: ast.AST, value: Any, reason: str) -> ast.Constant:
        orig_repr = PythonParser.unparse(original_node)
        new_node = ast.Constant(value=value)
        ast.copy_location(new_node, original_node)

        loc = PythonParser.get_location(original_node, filename=self.filename)
        self.tracker.record(
            pass_name="DecoderDetection",
            original=orig_repr,
            transformed=repr(value),
            confidence=Confidence.certain(reason, TransformationCategory.RECOVERED),
            location=loc,
        )
        self.num_decoded += 1
        return new_node


class DecoderDetectionPass(Pass):
    """Pass that detects and evaluates decoder invocations with constant arguments."""

    name = "DecoderDetection"
    description = "Evaluates base64, hex, unquote, and compression decoder calls."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        transformer = DecoderDetectionTransformer(tracker=tracker, filename=self.filename)
        return transformer.visit(target)
