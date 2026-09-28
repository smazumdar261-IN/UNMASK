"""Confidence assessment, scoring, and audit reporting engine.

Per Section 11 of the Master Specification (Phase 5: Confidence System):
- Categorical levels: CERTAIN, HIGH, MEDIUM, LOW, UNKNOWN
- Outcome types: Recovered, Inferred, Simplified, Unresolved
- Numerical values have explicit defined bases:
    * CERTAIN: 1.0 (syntactically/algebraically proven invariant)
    * HIGH:    0.85 (deterministic closed-scope analysis, standard library idioms)
    * MEDIUM:  0.50 (probabilistic pattern match or single-path heuristic)
    * LOW:     0.25 (speculative / partial transformation)
    * UNKNOWN: 0.00 (indeterminate / unresolved constructs)
- Auditing & reporting: distinguishes Recovered, Inferred, Simplified, and Unresolved.
- Formats: Text, JSON, and Markdown.
- Strict ordering and filtering support (--min-confidence).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence


class ConfidenceLevel(str, Enum):
    """Categorical confidence level for analysis and transformations."""

    CERTAIN = "CERTAIN"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"

    @property
    def rank(self) -> int:
        """Ordinal rank for confidence comparison."""
        ranks = {
            ConfidenceLevel.UNKNOWN: 0,
            ConfidenceLevel.LOW: 1,
            ConfidenceLevel.MEDIUM: 2,
            ConfidenceLevel.HIGH: 3,
            ConfidenceLevel.CERTAIN: 4,
        }
        return ranks[self]

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, ConfidenceLevel):
            return self.rank >= other.rank
        return NotImplemented

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, ConfidenceLevel):
            return self.rank > other.rank
        return NotImplemented

    def __le__(self, other: Any) -> bool:
        if isinstance(other, ConfidenceLevel):
            return self.rank <= other.rank
        return NotImplemented

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, ConfidenceLevel):
            return self.rank < other.rank
        return NotImplemented

    @classmethod
    def from_str(cls, s: str) -> "ConfidenceLevel":
        """Parse string to ConfidenceLevel, case-insensitively."""
        normalized = s.strip().upper()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown confidence level '{s}'. Expected: CERTAIN, HIGH, MEDIUM, LOW, UNKNOWN")


class TransformationCategory(str, Enum):
    """Classification of transformation outcomes."""

    RECOVERED = "Recovered"
    INFERRED = "Inferred"
    SIMPLIFIED = "Simplified"
    UNRESOLVED = "Unresolved"


@dataclass(frozen=True)
class Confidence:
    """Confidence value accompanied by justification, defined basis, and category."""

    level: ConfidenceLevel
    reason: str
    category: TransformationCategory = TransformationCategory.SIMPLIFIED
    score: float = 1.0

    @classmethod
    def certain(
        cls, reason: str, category: TransformationCategory = TransformationCategory.SIMPLIFIED
    ) -> "Confidence":
        """Mathematically or syntactically proven invariant (score=1.0)."""
        return cls(level=ConfidenceLevel.CERTAIN, reason=reason, category=category, score=1.0)

    @classmethod
    def high(
        cls, reason: str, category: TransformationCategory = TransformationCategory.SIMPLIFIED
    ) -> "Confidence":
        """Closed-scope standard analysis or high-certainty pattern (score=0.85)."""
        return cls(level=ConfidenceLevel.HIGH, reason=reason, category=category, score=0.85)

    @classmethod
    def medium(
        cls, reason: str, category: TransformationCategory = TransformationCategory.SIMPLIFIED
    ) -> "Confidence":
        """Probable transformation where edge cases may exist (score=0.50)."""
        return cls(level=ConfidenceLevel.MEDIUM, reason=reason, category=category, score=0.50)

    @classmethod
    def low(
        cls, reason: str, category: TransformationCategory = TransformationCategory.SIMPLIFIED
    ) -> "Confidence":
        """Heuristic or speculative transformation (score=0.25)."""
        return cls(level=ConfidenceLevel.LOW, reason=reason, category=category, score=0.25)

    @classmethod
    def unknown(
        cls, reason: str, category: TransformationCategory = TransformationCategory.UNRESOLVED
    ) -> "Confidence":
        """Indeterminate or unresolved construct (score=0.0)."""
        return cls(level=ConfidenceLevel.UNKNOWN, reason=reason, category=category, score=0.0)


class ConfidenceEngine:
    """Aggregates provenance records and produces comprehensive confidence reports."""

    def __init__(self, records: Optional[Sequence[Any]] = None) -> None:
        self.records: List[Any] = list(records) if records else []

    def add_record(self, record: Any) -> None:
        self.records.append(record)

    @property
    def total_count(self) -> int:
        return len(self.records)

    @property
    def level_breakdown(self) -> Dict[str, int]:
        """Count transformations grouped by ConfidenceLevel."""
        counts = {lvl.value: 0 for lvl in ConfidenceLevel}
        for r in self.records:
            counts[r.confidence.level.value] = counts.get(r.confidence.level.value, 0) + 1
        return counts

    @property
    def category_breakdown(self) -> Dict[str, int]:
        """Count transformations grouped by TransformationCategory."""
        counts = {cat.value: 0 for cat in TransformationCategory}
        for r in self.records:
            counts[r.confidence.category.value] = counts.get(r.confidence.category.value, 0) + 1
        return counts

    def compute_average_confidence(self) -> float:
        """Compute the weighted arithmetic mean confidence score [0.0 - 1.0]."""
        if not self.records:
            return 1.0
        total_score = sum(r.confidence.score for r in self.records)
        return round(total_score / len(self.records), 4)

    def filter_by_min_confidence(self, min_level: ConfidenceLevel) -> List[Any]:
        """Return all records meeting or exceeding the minimum confidence level."""
        return [r for r in self.records if r.confidence.level >= min_level]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize confidence audit metrics to a JSON-compatible dictionary."""
        return {
            "total_transformations": self.total_count,
            "average_confidence": self.compute_average_confidence(),
            "confidence_breakdown": self.level_breakdown,
            "category_breakdown": self.category_breakdown,
            "records": [
                {
                    "step_id": r.step_id,
                    "pass_name": r.pass_name,
                    "confidence_level": r.confidence.level.value,
                    "confidence_score": r.confidence.score,
                    "category": r.confidence.category.value,
                    "reason": r.confidence.reason,
                    "location": str(r.location),
                    "original": r.original,
                    "transformed": r.transformed,
                }
                for r in self.records
            ],
        }

    def format_text(self) -> str:
        """Render a readable plaintext audit report."""
        lines = [
            "==================================================",
            "        Universal Deobfuscator Audit Report       ",
            "==================================================",
            f"Total transformations applied: {self.total_count}",
            f"Average confidence score: {self.compute_average_confidence():.2f}",
            "",
            "Confidence Level Breakdown:",
        ]
        for lvl, cnt in self.level_breakdown.items():
            if cnt > 0:
                lines.append(f"  [{lvl}]: {cnt}")

        lines.extend(["", "Transformation Category Breakdown:"])
        for cat, cnt in self.category_breakdown.items():
            if cnt > 0:
                lines.append(f"  {cat}: {cnt}")

        if self.records:
            lines.extend(["", "Transformation Details:"])
            for r in self.records:
                cat_tag = f" ({r.confidence.category.value})"
                lines.append(
                    f"  - [{r.confidence.level.value}]{cat_tag} {r.pass_name} at {r.location}: {r.confidence.reason}"
                )

        lines.append("==================================================")
        return "\n".join(lines)

    def format_json(self, indent: int = 2) -> str:
        """Render JSON-formatted audit report."""
        return json.dumps(self.to_dict(), indent=indent)

    def format_markdown(self) -> str:
        """Render a GitHub-flavored Markdown audit report."""
        lines = [
            "# Universal Deobfuscator Audit Report",
            "",
            f"**Total Transformations:** {self.total_count}  ",
            f"**Average Confidence Score:** {self.compute_average_confidence():.2f}",
            "",
            "## Summary Metrics",
            "",
            "| Confidence Level | Count | Category | Count |",
            "| :--- | :--- | :--- | :--- |",
        ]
        levels = list(self.level_breakdown.items())
        categories = list(self.category_breakdown.items())
        max_rows = max(len(levels), len(categories))
        for i in range(max_rows):
            l_str = f"`{levels[i][0]}`: {levels[i][1]}" if i < len(levels) else ""
            c_str = f"**{categories[i][0]}**: {categories[i][1]}" if i < len(categories) else ""
            lines.append(f"| {l_str} | | {c_str} | |")

        if self.records:
            lines.extend([
                "",
                "## Transformation Details",
                "",
                "| Step | Pass | Level | Category | Location | Reason |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ])
            for r in self.records:
                lines.append(
                    f"| {r.step_id} | {r.pass_name} | `{r.confidence.level.value}` | "
                    f"{r.confidence.category.value} | `{r.location}` | {r.confidence.reason} |"
                )

        return "\n".join(lines)
