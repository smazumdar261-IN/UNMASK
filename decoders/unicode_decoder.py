"""Unicode escape sequence decoder plugin.

Per Section 7 of the Master Specification:
- Decodes Unicode escape sequences: \\uXXXX, \\UXXXXXXXX, and \\xXX.
"""

import re
from typing import Any, Tuple

from core.confidence import Confidence, TransformationCategory
from decoders.registry import BaseDecoder

UNICODE_ESCAPE_RE = re.compile(r"(?:\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{8}|\\x[0-9a-fA-F]{2})")


class UnicodeDecoder(BaseDecoder):
    """Decodes Unicode and hexadecimal escaped string literals."""

    name = "UnicodeDecoder"
    description = "Decodes Unicode escape sequences (\\uXXXX, \\UXXXXXXXX) to readable characters."

    def can_decode(self, data: Any) -> bool:
        if not isinstance(data, str):
            return False
        # Needs at least one unicode escape pattern
        return bool(UNICODE_ESCAPE_RE.search(data))

    def decode(self, data: Any) -> Tuple[bool, Any, str]:
        if not isinstance(data, str):
            return False, data, "Input must be string"

        if not self.can_decode(data):
            return False, data, "No Unicode escape sequences found"

        try:
            # Safely decode raw escape sequences
            decoded = data.encode("utf-8").decode("unicode_escape")
            if decoded != data:
                return True, decoded, "Decoded Unicode escape sequences"
            return False, data, "No transformation occurred"
        except Exception as e:
            return False, data, f"Unicode escape decoding failed: {e}"

    def confidence(self, data: Any, result: Any) -> Confidence:
        return Confidence.certain("Decoded Unicode escape sequences to characters", TransformationCategory.RECOVERED)
