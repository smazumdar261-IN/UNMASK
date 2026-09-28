"""Provenance and audit tracking system.

Per Rule 6 and Section 11 of the Master Specification:
Every important transformation is traceable with source location, original code,
transformed code, confidence, and reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from core.confidence import Confidence, ConfidenceEngine, ConfidenceLevel, TransformationCategory


@dataclass(frozen=True)
class SourceLocation:
    """Represents a location span in source text."""

    filename: Optional[str] = None
    start_line: Optional[int] = None
    start_col: Optional[int] = None
    end_line: Optional[int] = None
    end_col: Optional[int] = None

    def __str__(self) -> str:
        parts = []
        if self.filename:
            parts.append(self.filename)
        if self.start_line is not None:
            span = f"L{self.start_line}"
            if self.start_col is not None:
                span += f":{self.start_col}"
            if self.end_line is not None:
                if self.end_line != self.start_line or (self.end_col is not None and self.end_col != self.start_col):
                    span += f"-L{self.end_line}"
                    if self.end_col is not None:
                        span += f":{self.end_col}"
            parts.append(span)
        return ":".join(parts) if parts else "<unknown>"


@dataclass
class ProvenanceRecord:
    """Detailed record of a single transformation step."""

    step_id: int
    pass_name: str
    original: str
    transformed: str
    confidence: Confidence
    location: SourceLocation = field(default_factory=SourceLocation)

    def summary(self) -> str:
        return (
            f"[{self.confidence.level.value}] {self.pass_name} at {self.location}: "
            f"{self.confidence.reason}"
        )


class ProvenanceTracker:
    """Collects, filters, and audits provenance records across transformation passes."""

    def __init__(self, min_confidence: ConfidenceLevel = ConfidenceLevel.LOW) -> None:
        self._records: List[ProvenanceRecord] = []
        self._counter: int = 0
        self.min_confidence: ConfidenceLevel = min_confidence

    def is_allowed(self, level: ConfidenceLevel) -> bool:
        """Check if a transformation at level satisfies the minimum confidence threshold."""
        return level >= self.min_confidence

    def record(
        self,
        pass_name: str,
        original: str,
        transformed: str,
        confidence: Confidence,
        location: Optional[SourceLocation] = None,
    ) -> ProvenanceRecord:
        """Register a transformation record."""
        self._counter += 1
        entry = ProvenanceRecord(
            step_id=self._counter,
            pass_name=pass_name,
            original=original,
            transformed=transformed,
            confidence=confidence,
            location=location or SourceLocation(),
        )
        self._records.append(entry)
        return entry

    def record_unresolved(
        self,
        pass_name: str,
        original: str,
        reason: str,
        location: Optional[SourceLocation] = None,
    ) -> ProvenanceRecord:
        """Register an unresolved or ambiguous construct that could not be safely transformed."""
        confidence = Confidence.unknown(reason=reason, category=TransformationCategory.UNRESOLVED)
        return self.record(
            pass_name=pass_name,
            original=original,
            transformed="[unresolved]",
            confidence=confidence,
            location=location,
        )

    @property
    def records(self) -> List[ProvenanceRecord]:
        return list(self._records)

    def count_by_level(self, level: ConfidenceLevel) -> int:
        return sum(1 for r in self._records if r.confidence.level == level)

    def count_by_category(self, category: TransformationCategory) -> int:
        return sum(1 for r in self._records if r.confidence.category == category)

    def get_engine(self) -> ConfidenceEngine:
        """Return a ConfidenceEngine bound to current records."""
        return ConfidenceEngine(self._records)

    def format_report(self, format_type: str = "text") -> str:
        """Format audit report into text, json, or markdown."""
        engine = self.get_engine()
        fmt = format_type.lower().strip()
        if fmt == "json":
            return engine.format_json()
        elif fmt in ("markdown", "md"):
            return engine.format_markdown()
        else:
            return engine.format_text()

    def clear(self) -> None:
        self._records.clear()
        self._counter = 0
