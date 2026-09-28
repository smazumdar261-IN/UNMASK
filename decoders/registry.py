"""Decoder plugin architecture and registry.

Per Section 17 of the Master Specification:
- Decoders must be modular plugins registered in a registry.
- Each decoder exposes: name, can_decode(), decode(), confidence(), explain().
- A decoder should never crash the pipeline because an input is malformed.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from core.confidence import Confidence, ConfidenceLevel, TransformationCategory


class BaseDecoder(ABC):
    """Abstract interface for all deobfuscation decoders."""

    name: str = "BaseDecoder"
    description: str = "Base decoder plugin"

    @abstractmethod
    def can_decode(self, data: Any) -> bool:
        """Return True if the decoder can potentially decode the given input data."""
        pass

    @abstractmethod
    def decode(self, data: Any) -> Tuple[bool, Any, str]:
        """Attempt to decode data.

        Returns:
            (success: bool, result: Any, explanation: str)
            Never raises exceptions. On failure, returns (False, data, error_reason).
        """
        pass

    @abstractmethod
    def confidence(self, data: Any, result: Any) -> Confidence:
        """Return the confidence score and justification for the decoded result."""
        pass

    def explain(self, data: Any) -> str:
        """Provide a human-readable explanation of what this decoder would do to data."""
        return f"{self.name}: decodes {type(data).__name__} input"


class DecoderRegistry:
    """Registry managing available decoder plugins."""

    def __init__(self) -> None:
        self._decoders: Dict[str, BaseDecoder] = {}
        self._order: List[str] = []

    def register(self, decoder: BaseDecoder) -> None:
        """Register a new decoder instance."""
        key = decoder.name.lower()
        self._decoders[key] = decoder
        if key not in self._order:
            self._order.append(key)

    def get(self, name: str) -> Optional[BaseDecoder]:
        """Get a decoder by name (case-insensitive)."""
        return self._decoders.get(name.lower())

    def find_matching_decoders(self, data: Any) -> List[BaseDecoder]:
        """Find all decoders that claim to be able to decode data."""
        matches = []
        for key in self._order:
            decoder = self._decoders[key]
            try:
                if decoder.can_decode(data):
                    matches.append(decoder)
            except Exception:
                continue
        return matches

    @property
    def decoders(self) -> List[BaseDecoder]:
        return [self._decoders[k] for k in self._order]


# Global decoder registry
decoder_registry = DecoderRegistry()
