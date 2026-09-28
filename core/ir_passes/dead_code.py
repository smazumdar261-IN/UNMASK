"""Language-independent dead code elimination pass for Common Intermediate Representation.

Per Section 16 & Phase 10:
Prunes dead branches, dead loops, and unreachable statements post-return in Common IR.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from core.confidence import Confidence, TransformationCategory
from core.ir import (
    IRBranch,
    IRBreak,
    IRConstant,
    IRContinue,
    IRFunction,
    IRLoop,
    IRModule,
    IRRaise,
    IRReturn,
    IRStatement,
    IRTransformer,
    format_ir,
)
from core.pipeline import Pass
from core.provenance import ProvenanceTracker, SourceLocation


class IRDeadCodeEliminationTransformer(IRTransformer):
    """Eliminates dead branches, dead loops, and unreachable statements in Common IR."""

    def __init__(self, tracker: Optional[ProvenanceTracker] = None) -> None:
        self.tracker = tracker

    def visit_IRModule(self, node: IRModule) -> IRModule:
        node.body = self._clean_statements(node.body)
        return node

    def visit_IRFunction(self, node: IRFunction) -> IRFunction:
        node.body = self._clean_statements(node.body)
        return node

    def _clean_statements(self, statements: List[IRStatement]) -> List[IRStatement]:
        cleaned: List[IRStatement] = []
        terminal_hit = False

        for stmt in statements:
            if terminal_hit:
                # Discard unreachable statement
                orig_text = format_ir(stmt)
                loc = stmt.location or SourceLocation()
                if self.tracker:
                    self.tracker.record(
                        pass_name="IRDeadCodeElimination",
                        original=orig_text,
                        transformed="/* removed unreachable */",
                        confidence=Confidence.certain(
                            reason=f"Eliminated unreachable code following terminal statement: {orig_text}",
                            category=TransformationCategory.SIMPLIFIED,
                        ),
                        location=loc,
                    )
                continue

            # Process statement
            if isinstance(stmt, IRBranch):
                stmt.condition = self.visit(stmt.condition)
                stmt.body = self._clean_statements(stmt.body)
                stmt.orelse = self._clean_statements(stmt.orelse)

                if isinstance(stmt.condition, IRConstant):
                    cond_val = bool(stmt.condition.value)
                    orig_text = format_ir(stmt)
                    loc = stmt.location or SourceLocation()

                    if cond_val:
                        # True branch: replace with body
                        replacement = stmt.body
                        if self.tracker:
                            self.tracker.record(
                                pass_name="IRDeadCodeElimination",
                                original=orig_text,
                                transformed="\n".join(format_ir(s) for s in replacement) or "pass",
                                confidence=Confidence.certain(
                                    reason="Pruned dead else branch of constant True condition",
                                    category=TransformationCategory.SIMPLIFIED,
                                ),
                                location=loc,
                            )
                        cleaned.extend(replacement)
                        continue
                    else:
                        # False branch: replace with orelse
                        replacement = stmt.orelse
                        if self.tracker:
                            self.tracker.record(
                                pass_name="IRDeadCodeElimination",
                                original=orig_text,
                                transformed="\n".join(format_ir(s) for s in replacement) or "pass",
                                confidence=Confidence.certain(
                                    reason="Pruned dead then branch of constant False condition",
                                    category=TransformationCategory.SIMPLIFIED,
                                ),
                                location=loc,
                            )
                        cleaned.extend(replacement)
                        continue

                cleaned.append(stmt)

            elif isinstance(stmt, IRLoop):
                if stmt.condition is not None:
                    stmt.condition = self.visit(stmt.condition)
                stmt.body = self._clean_statements(stmt.body)
                stmt.orelse = self._clean_statements(stmt.orelse)

                if isinstance(stmt.condition, IRConstant) and not bool(stmt.condition.value):
                    # Dead loop: condition is false
                    orig_text = format_ir(stmt)
                    loc = stmt.location or SourceLocation()
                    replacement = stmt.orelse
                    if self.tracker:
                        self.tracker.record(
                            pass_name="IRDeadCodeElimination",
                            original=orig_text,
                            transformed="\n".join(format_ir(s) for s in replacement) or "pass",
                            confidence=Confidence.certain(
                                reason="Eliminated loop with constant False condition",
                                category=TransformationCategory.SIMPLIFIED,
                            ),
                            location=loc,
                        )
                    cleaned.extend(replacement)
                    continue

                cleaned.append(stmt)

            else:
                res = self.visit(stmt)
                if res is not None:
                    if isinstance(res, list):
                        cleaned.extend(res)
                    else:
                        cleaned.append(res)

            # Check if this statement is terminal
            if isinstance(stmt, (IRReturn, IRBreak, IRContinue, IRRaise)):
                terminal_hit = True

        return cleaned


class IRDeadCodeElimination(Pass):
    """Language-independent dead code elimination pass on Common IR."""

    name = "IRDeadCodeElimination"
    description = "Eliminates dead branches, dead loops, and unreachable statements in Common IR"

    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        transformer = IRDeadCodeEliminationTransformer(tracker=tracker)
        return transformer.visit(target)
