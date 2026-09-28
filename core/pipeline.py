"""Pipeline and transformation pass abstraction.

Per Section 1 & Section 6 of the Master Specification:
- Pipeline executes passes sequentially.
- Conservative behavior: transformations preserve semantics or remain unchanged.
- Provenance is collected and audited.
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, List, Optional
from core.confidence import Confidence, ConfidenceLevel
from core.provenance import ProvenanceTracker

logger = logging.getLogger("universal_deobfuscator.pipeline")


class Pass(ABC):
    """Abstract base class for analysis or transformation passes."""

    name: str = "BasePass"
    description: str = "Base transformation pass"

    @abstractmethod
    def run(self, target: Any, tracker: ProvenanceTracker) -> Any:
        """Execute the pass on the target (AST or IR), recording provenance."""
        pass


class Pipeline:
    """Sequential execution pipeline for transformation passes."""

    def __init__(
        self,
        passes: Optional[List[Pass]] = None,
        tracker: Optional[ProvenanceTracker] = None,
        min_confidence: ConfidenceLevel = ConfidenceLevel.LOW,
    ) -> None:
        self.passes: List[Pass] = passes or []
        self.tracker: ProvenanceTracker = tracker or ProvenanceTracker(min_confidence=min_confidence)

    def add_pass(self, p: Pass) -> "Pipeline":
        self.passes.append(p)
        return self

    def execute(self, target: Any, max_iterations: int = 1, until_convergence: bool = False) -> Any:
        """Run all registered passes sequentially.

        Args:
            target: AST or IR target.
            max_iterations: Maximum iterations across the pass sequence.
            until_convergence: If True, loop until no further changes occur (bounded by max_iterations).
        """
        current = target
        limit = max_iterations if not until_convergence else max(max_iterations, 10)

        for iteration in range(limit):
            initial_count = len(self.tracker.records)
            for p in self.passes:
                logger.debug(f"[Iter {iteration + 1}] Starting pass: {p.name}")
                try:
                    current = p.run(current, self.tracker)
                except Exception as e:
                    logger.error(f"Pass {p.name} failed with error: {e}", exc_info=True)
                    raise
                logger.debug(f"[Iter {iteration + 1}] Completed pass: {p.name}")

            # Check if any transformations were applied in this iteration
            if until_convergence and len(self.tracker.records) == initial_count:
                logger.debug(f"Pipeline converged after {iteration + 1} iterations.")
                break

        return current

    def generate_report(self, format_type: str = "text") -> str:
        """Generate an audit report from provenance records in requested format (text, json, markdown)."""
        return self.tracker.format_report(format_type)
