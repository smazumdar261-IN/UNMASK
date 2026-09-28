"""String reconstruction pass for Python AST.

Phase 1C: Static string reconstruction.
Reconstructs fragmented, obscured, or generated strings:
- chr() / ord() static evaluation: chr(72) -> 'H', ord('A') -> 65
- String/bytes join: "".join(["a", "b"]) -> "ab"
- Byte array decode: bytes([72, 101, 108, 108, 111]).decode() -> "Hello"
- Constant bytes decode: b"Hello".decode("utf-8") -> "Hello"
- String formatting: "{}".format("val"), "%s" % "val"
- Constant f-string flattening (JoinedStr)

Guarantees:
- Strict encoding allowlist (no dynamic / arbitrary code execution)
- Memory limits on reconstructed string sizes
- Provenance recording for every reconstructed string
"""

import ast
from typing import Any, List, Optional, Set

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation
from languages.python.parser import PythonParser
from passes.expression_folding import extract_constant_value, is_safe_constant

MAX_STR_LEN = 65536

ALLOWED_ENCODINGS: Set[str] = {
    "utf-8",
    "utf8",
    "ascii",
    "latin-1",
    "latin1",
    "iso-8859-1",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "utf-32",
    "utf-32-le",
    "utf-32-be",
    "raw_unicode_escape",
    "unicode_escape",
}

ALLOWED_DECODE_ERRORS: Set[str] = {"strict", "ignore", "replace"}


class StringReconstructionTransformer(ast.NodeTransformer):
    """AST transformer that reconstructs obscured and fragmented string expressions."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        super().__init__()
        self.tracker = tracker
        self.filename = filename
        self.num_reconstructed = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # Bottom-up traversal
        self.generic_visit(node)

        # 1. chr(int)
        if isinstance(node.func, ast.Name) and node.func.id == "chr" and len(node.args) == 1:
            if is_safe_constant(node.args[0]):
                val = extract_constant_value(node.args[0])
                if isinstance(val, int) and 0 <= val <= 0x10FFFF:
                    try:
                        char = chr(val)
                        return self._replace_with_constant(
                            node,
                            char,
                            f"Evaluated chr({val}) -> {repr(char)}",
                        )
                    except Exception:
                        pass

        # 2. ord(str)
        if isinstance(node.func, ast.Name) and node.func.id == "ord" and len(node.args) == 1:
            if is_safe_constant(node.args[0]):
                val = extract_constant_value(node.args[0])
                if isinstance(val, (str, bytes)) and len(val) == 1:
                    try:
                        code = ord(val)
                        return self._replace_with_constant(
                            node,
                            code,
                            f"Evaluated ord({repr(val)}) -> {code}",
                        )
                    except Exception:
                        pass

        # 3. bytes([int, ...]) or bytearray([int, ...])
        if isinstance(node.func, ast.Name) and node.func.id in ("bytes", "bytearray") and len(node.args) == 1:
            if isinstance(node.args[0], (ast.List, ast.Tuple)):
                elts = node.args[0].elts
                if all(is_safe_constant(el) for el in elts):
                    int_vals = [extract_constant_value(el) for el in elts]
                    if all(isinstance(v, int) and 0 <= v <= 255 for v in int_vals):
                        if len(int_vals) <= MAX_STR_LEN:
                            try:
                                b_val = bytes(int_vals)
                                return self._replace_with_constant(
                                    node,
                                    b_val,
                                    f"Constructed bytes from {len(int_vals)} byte integers",
                                )
                            except Exception:
                                pass

        # 4. Method calls: .join(), .decode(), .encode(), .format()
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.ctx, ast.Load):
            attr_name = node.func.attr
            caller_node = node.func.value

            # 4a. sep.join(iterable)
            if attr_name == "join" and is_safe_constant(caller_node) and len(node.args) == 1:
                sep = extract_constant_value(caller_node)
                if isinstance(sep, (str, bytes)):
                    items: Optional[List[Any]] = None
                    if isinstance(node.args[0], (ast.List, ast.Tuple)):
                        if all(is_safe_constant(el) for el in node.args[0].elts):
                            items = [extract_constant_value(el) for el in node.args[0].elts]
                    elif is_safe_constant(node.args[0]):
                        candidate = extract_constant_value(node.args[0])
                        if isinstance(candidate, (list, tuple)):
                            items = list(candidate)

                    if items is not None:
                        if all(isinstance(it, type(sep)) for it in items):
                            total_len = sum(len(it) for it in items) + len(sep) * max(0, len(items) - 1)
                            if total_len <= MAX_STR_LEN:
                                try:
                                    joined = sep.join(items)
                                    return self._replace_with_constant(
                                        node,
                                        joined,
                                        f"Evaluated {repr(sep)}.join() on {len(items)} elements",
                                    )
                                except Exception:
                                    pass

            # 4b. bytes.decode(encoding="utf-8", errors="strict")
            if attr_name == "decode" and is_safe_constant(caller_node):
                b_val = extract_constant_value(caller_node)
                if isinstance(b_val, (bytes, bytearray)):
                    encoding = "utf-8"
                    errors = "strict"

                    if len(node.args) >= 1:
                        if not is_safe_constant(node.args[0]):
                            return node
                        enc_cand = extract_constant_value(node.args[0])
                        if not isinstance(enc_cand, str):
                            return node
                        encoding = enc_cand

                    if len(node.args) >= 2:
                        if not is_safe_constant(node.args[1]):
                            return node
                        err_cand = extract_constant_value(node.args[1])
                        if not isinstance(err_cand, str):
                            return node
                        errors = err_cand

                    # Handle keyword arguments
                    for kw in node.keywords:
                        if kw.arg == "encoding" and is_safe_constant(kw.value):
                            encoding = extract_constant_value(kw.value)
                        elif kw.arg == "errors" and is_safe_constant(kw.value):
                            errors = extract_constant_value(kw.value)

                    clean_enc = encoding.lower().replace("_", "-")
                    if clean_enc in ALLOWED_ENCODINGS and errors in ALLOWED_DECODE_ERRORS:
                        try:
                            decoded_str = b_val.decode(encoding, errors)
                            if len(decoded_str) <= MAX_STR_LEN:
                                return self._replace_with_constant(
                                    node,
                                    decoded_str,
                                    f"Decoded {len(b_val)} bytes with '{encoding}'",
                                )
                        except Exception:
                            pass

            # 4c. str.encode(encoding="utf-8")
            if attr_name == "encode" and is_safe_constant(caller_node):
                s_val = extract_constant_value(caller_node)
                if isinstance(s_val, str):
                    encoding = "utf-8"
                    if len(node.args) >= 1 and is_safe_constant(node.args[0]):
                        enc_cand = extract_constant_value(node.args[0])
                        if isinstance(enc_cand, str):
                            encoding = enc_cand

                    clean_enc = encoding.lower().replace("_", "-")
                    if clean_enc in ALLOWED_ENCODINGS:
                        try:
                            encoded_bytes = s_val.encode(encoding)
                            if len(encoded_bytes) <= MAX_STR_LEN:
                                return self._replace_with_constant(
                                    node,
                                    encoded_bytes,
                                    f"Encoded string with '{encoding}'",
                                )
                        except Exception:
                            pass

            # 4d. str.format(*args, **kwargs)
            if attr_name == "format" and is_safe_constant(caller_node):
                fmt_val = extract_constant_value(caller_node)
                if isinstance(fmt_val, str):
                    if all(is_safe_constant(arg) for arg in node.args) and all(
                        is_safe_constant(kw.value) for kw in node.keywords
                    ):
                        args_list = [extract_constant_value(arg) for arg in node.args]
                        kwargs_dict = {kw.arg: extract_constant_value(kw.value) for kw in node.keywords if kw.arg}
                        try:
                            formatted = fmt_val.format(*args_list, **kwargs_dict)
                            if len(formatted) <= MAX_STR_LEN:
                                return self._replace_with_constant(
                                    node,
                                    formatted,
                                    "Evaluated str.format() with constant arguments",
                                )
                        except Exception:
                            pass

        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)

        # Handle printf-style formatting: "%s-%d" % ("val", 42)
        if isinstance(node.op, ast.Mod) and is_safe_constant(node.left):
            fmt_str = extract_constant_value(node.left)
            if isinstance(fmt_str, (str, bytes)):
                args: Any = None
                if is_safe_constant(node.right):
                    args = extract_constant_value(node.right)
                elif isinstance(node.right, (ast.Tuple, ast.List)):
                    if all(is_safe_constant(el) for el in node.right.elts):
                        args = tuple(extract_constant_value(el) for el in node.right.elts)

                if args is not None:
                    try:
                        formatted = fmt_str % args
                        if len(formatted) <= MAX_STR_LEN:
                            return self._replace_with_constant(
                                node,
                                formatted,
                                "Evaluated %-style string formatting",
                            )
                    except Exception:
                        pass

        return node

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        self.generic_visit(node)

        # Check if every component is a constant or formatted constant
        parts: List[str] = []
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                parts.append(val.value)
            elif isinstance(val, ast.FormattedValue):
                if is_safe_constant(val.value):
                    inner_val = extract_constant_value(val.value)
                    spec = ""
                    if val.format_spec:
                        if isinstance(val.format_spec, ast.JoinedStr) and all(
                            isinstance(v, ast.Constant) for v in val.format_spec.values
                        ):
                            spec = "".join(v.value for v in val.format_spec.values if isinstance(v.value, str))
                        else:
                            return node
                    try:
                        formatted_part = format(inner_val, spec)
                        parts.append(formatted_part)
                    except Exception:
                        return node
                else:
                    return node
            else:
                return node

        full_str = "".join(parts)
        if len(full_str) <= MAX_STR_LEN:
            return self._replace_with_constant(
                node,
                full_str,
                f"Reconstructed constant f-string from {len(parts)} parts",
            )

        return node

    def _replace_with_constant(self, original_node: ast.AST, value: Any, reason: str) -> ast.Constant:
        orig_repr = PythonParser.unparse(original_node)
        new_node = ast.Constant(value=value)
        ast.copy_location(new_node, original_node)

        loc = PythonParser.get_location(original_node, filename=self.filename)
        self.tracker.record(
            pass_name="StringReconstruction",
            original=orig_repr,
            transformed=repr(value),
            confidence=Confidence.certain(reason, TransformationCategory.RECOVERED),
            location=loc,
        )
        self.num_reconstructed += 1
        return new_node


class StringReconstructionPass(Pass):
    """Pass that reconstructs obscured and fragmented string expressions in Python AST."""

    name = "StringReconstruction"
    description = "Reconstructs strings from chr(), bytes.decode(), ''.join(), and format operations."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        if not isinstance(target, ast.AST):
            return target

        transformer = StringReconstructionTransformer(tracker=tracker, filename=self.filename)
        return transformer.visit(target)
