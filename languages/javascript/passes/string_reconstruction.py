"""JavaScript string reconstruction and pattern recovery pass.

Per Section 12 of the Master Specification:
Reconstructs obfuscated strings in JavaScript:
- String.fromCharCode(72, 101, 108, 108, 111) -> 'Hello'
- ['H', 'e', 'l', 'l', 'o'].join('') -> 'Hello'
- String reversal: 'olleh'.split('').reverse().join('') -> 'hello'
- String split on constants: 'a,b,c'.split(',') -> ['a', 'b', 'c']
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.confidence import Confidence, TransformationCategory
from core.pipeline import Pass
from core.provenance import ProvenanceTracker
from languages.javascript.ast_nodes import (
    JSArrayExpression,
    JSCallExpression,
    JSIdentifier,
    JSLiteral,
    JSMemberExpression,
    JSNode,
)
from languages.javascript.printer import JSPrinter
from languages.javascript.transformer import JSTransformer


class JSStringReconstructionTransformer(JSTransformer):
    """Reconstructs strings from character codes, array joins, and reversals."""

    def __init__(self, tracker: ProvenanceTracker, filename: Optional[str] = None) -> None:
        self.tracker = tracker
        self.filename = filename

    def visit_JSCallExpression(self, node: JSCallExpression) -> Any:
        self.generic_visit(node)

        # 1. String reversal idiom: s.split('').reverse().join('')
        reversed_str = self._try_eval_string_reversal(node)
        if reversed_str is not None:
            return self._record_and_replace(node, reversed_str, "String reversal via split.reverse.join")

        # 2. String.fromCharCode(c1, c2, ...)
        from_char_code = self._try_eval_from_char_code(node)
        if from_char_code is not None:
            return self._record_and_replace(node, from_char_code, "String.fromCharCode evaluation")

        # 3. Array join: [c1, c2].join(sep)
        joined_str = self._try_eval_array_join(node)
        if joined_str is not None:
            return self._record_and_replace(node, joined_str, "Array.join string reconstruction")

        # 4. String split: 'a,b,c'.split(',')
        split_arr = self._try_eval_string_split(node)
        if split_arr is not None:
            orig_src = JSPrinter.print_code(node)
            res_node = JSArrayExpression(
                elements=[JSLiteral(value=s, raw=repr(s), location=node.location) for s in split_arr],
                location=node.location,
            )
            self.tracker.record(
                pass_name="JSStringReconstruction",
                original=orig_src,
                transformed=JSPrinter.print_code(res_node),
                confidence=Confidence.certain(
                    "Statically evaluated String.split on constant literal",
                    TransformationCategory.SIMPLIFIED,
                ),
                location=node.location,
            )
            return res_node

        return node

    def _try_eval_string_reversal(self, node: JSCallExpression) -> Optional[str]:
        """Check for pattern: <str_literal>.split('').reverse().join('')."""
        # Outer call: .join(...)
        if not (isinstance(node.callee, JSMemberExpression) and not node.callee.computed):
            return None
        if not (isinstance(node.callee.property, JSIdentifier) and node.callee.property.name == "join"):
            return None
        if len(node.arguments) > 1:
            return None
        join_sep = ""
        if len(node.arguments) == 1:
            if not (isinstance(node.arguments[0], JSLiteral) and isinstance(node.arguments[0].value, str)):
                return None
            join_sep = node.arguments[0].value
        if join_sep != "":
            return None

        # Middle call: .reverse()
        reverse_call = node.callee.object
        if not (isinstance(reverse_call, JSCallExpression) and isinstance(reverse_call.callee, JSMemberExpression)):
            return None
        if not (isinstance(reverse_call.callee.property, JSIdentifier) and reverse_call.callee.property.name == "reverse"):
            return None

        # Inner call / target: .split('') or array literal [c1, c2, ...]
        target_obj = reverse_call.callee.object
        if isinstance(target_obj, JSArrayExpression):
            chars = []
            for el in target_obj.elements:
                if isinstance(el, JSLiteral) and isinstance(el.value, str):
                    chars.append(el.value)
                else:
                    return None
            return "".join(reversed(chars))

        if isinstance(target_obj, JSCallExpression) and isinstance(target_obj.callee, JSMemberExpression):
            if isinstance(target_obj.callee.property, JSIdentifier) and target_obj.callee.property.name == "split":
                if len(target_obj.arguments) == 1 and isinstance(target_obj.arguments[0], JSLiteral) and target_obj.arguments[0].value == "":
                    target_str_node = target_obj.callee.object
                    if isinstance(target_str_node, JSLiteral) and isinstance(target_str_node.value, str):
                        return target_str_node.value[::-1]

        return None

    def _try_eval_from_char_code(self, node: JSCallExpression) -> Optional[str]:
        """Check for String.fromCharCode(n1, n2, ...)."""
        callee = node.callee
        if not (isinstance(callee, JSMemberExpression) and not callee.computed):
            return None
        if not (isinstance(callee.object, JSIdentifier) and callee.object.name == "String"):
            return None
        if not (isinstance(callee.property, JSIdentifier) and callee.property.name == "fromCharCode"):
            return None

        # All arguments must be integer literals
        if not node.arguments:
            return ""

        chars: List[str] = []
        for arg in node.arguments:
            if isinstance(arg, JSLiteral) and isinstance(arg.value, int) and 0 <= arg.value <= 0x10FFFF:
                chars.append(chr(arg.value))
            else:
                return None

        return "".join(chars)

    def _try_eval_array_join(self, node: JSCallExpression) -> Optional[str]:
        """Check for [c1, c2, ...].join(sep)."""
        callee = node.callee
        if not (isinstance(callee, JSMemberExpression) and not callee.computed):
            return None
        if not (isinstance(callee.property, JSIdentifier) and callee.property.name == "join"):
            return None
        if not isinstance(callee.object, JSArrayExpression):
            return None

        sep = ","
        if len(node.arguments) == 1:
            if isinstance(node.arguments[0], JSLiteral) and isinstance(node.arguments[0].value, str):
                sep = node.arguments[0].value
            else:
                return None
        elif len(node.arguments) > 1:
            return None

        elements: List[str] = []
        for el in callee.object.elements:
            if isinstance(el, JSLiteral) and el.value is not None:
                elements.append(str(el.value))
            else:
                return None

        return sep.join(elements)

    def _try_eval_string_split(self, node: JSCallExpression) -> Optional[List[str]]:
        """Check for 'a,b,c'.split(',')."""
        callee = node.callee
        if not (isinstance(callee, JSMemberExpression) and not callee.computed):
            return None
        if not (isinstance(callee.property, JSIdentifier) and callee.property.name == "split"):
            return None
        if not (isinstance(callee.object, JSLiteral) and isinstance(callee.object.value, str)):
            return None
        if len(node.arguments) != 1:
            return None
        if not (isinstance(node.arguments[0], JSLiteral) and isinstance(node.arguments[0].value, str)):
            return None

        src_str = callee.object.value
        delim = node.arguments[0].value
        return src_str.split(delim) if delim != "" else list(src_str)

    def _record_and_replace(self, node: JSNode, result_str: str, reason: str) -> JSLiteral:
        orig_src = JSPrinter.print_code(node)
        res_node = JSLiteral(value=result_str, raw=repr(result_str), location=node.location)
        self.tracker.record(
            pass_name="JSStringReconstruction",
            original=orig_src,
            transformed=JSPrinter.print_code(res_node),
            confidence=Confidence.certain(reason, TransformationCategory.RECOVERED),
            location=node.location,
        )
        return res_node


class JSStringReconstructionPass(Pass):
    """Pass that reconstructs strings from character codes and array joins."""

    name = "JSStringReconstruction"
    description = "Reconstructs strings from String.fromCharCode, array.join, and string reversals."

    def __init__(self, filename: Optional[str] = None) -> None:
        self.filename = filename

    def run(self, target: Any, tracker: Optional[ProvenanceTracker] = None) -> Any:
        if not isinstance(target, JSNode):
            return target
        trk = tracker or ProvenanceTracker()
        transformer = JSStringReconstructionTransformer(trk, self.filename)
        return transformer.visit(target)
