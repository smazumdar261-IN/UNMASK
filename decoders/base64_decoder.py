"""Base64 decoder plugin.

Per Section 7 & Section 17 of the Master Specification:
- Supports standard and URL-safe Base64 decoding.
- Strictly validates input to avoid false positives (does not decode every 4-char string).
- Assesses confidence based on printability and entropy of decoded content.
"""

import base64
import re
import string
from typing import Any, Tuple

from core.confidence import Confidence, ConfidenceLevel, TransformationCategory
from decoders.registry import BaseDecoder

# Valid Base64 pattern (min 4 characters, proper padding if present)
B64_STANDARD_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
B64_URLSAFE_RE = re.compile(r"^[A-Za-z0-9\-_]+={0,2}$")
PRINTABLE_BYTES = set(bytes(string.printable, "ascii"))


def is_mostly_printable(data: bytes, threshold: float = 0.85) -> bool:
    """Return True if at least threshold ratio of bytes are printable ASCII."""
    if not data:
        return False
    printable_count = sum(1 for b in data if b in PRINTABLE_BYTES)
    return (printable_count / len(data)) >= threshold


class Base64Decoder(BaseDecoder):
    """Decodes standard and URL-safe Base64 encoded strings/bytes."""

    name = "Base64Decoder"
    description = "Decodes standard and URL-safe Base64 data."

    def can_decode(self, data: Any) -> bool:
        if not isinstance(data, (str, bytes)):
            return False

        text = data.decode("ascii", errors="ignore") if isinstance(data, bytes) else data
        text = text.strip()

        # Reject short inputs to prevent false positives on common 4-letter words
        if len(text) < 4 or len(text) % 4 not in (0, 2, 3):
            return False

        # Must strictly match base64 character sets
        if not (B64_STANDARD_RE.match(text) or B64_URLSAFE_RE.match(text)):
            return False

        # Attempt trial decode to verify validity
        try:
            # Add padding if missing
            missing_padding = (4 - len(text) % 4) % 4
            padded = text + ("=" * missing_padding)
            decoded = base64.b64decode(padded, validate=True)
            return len(decoded) > 0
        except Exception:
            try:
                decoded = base64.urlsafe_b64decode(padded)
                return len(decoded) > 0
            except Exception:
                return False

    def decode(self, data: Any, to_text: bool = False) -> Tuple[bool, Any, str]:
        if not isinstance(data, (str, bytes)):
            return False, data, "Input must be str or bytes"

        text = data.decode("ascii", errors="ignore") if isinstance(data, bytes) else data
        text = text.strip()

        missing_padding = (4 - len(text) % 4) % 4
        padded = text + ("=" * missing_padding)

        # Try standard b64decode
        try:
            decoded_bytes = base64.b64decode(padded, validate=False)
            if to_text:
                try:
                    decoded_text = decoded_bytes.decode("utf-8")
                    if is_mostly_printable(decoded_bytes):
                        return True, decoded_text, "Decoded Base64 to UTF-8 text"
                except UnicodeDecodeError:
                    pass
            return True, decoded_bytes, "Decoded Base64 to bytes"
        except Exception:
            pass

        # Try urlsafe_b64decode
        try:
            decoded_bytes = base64.urlsafe_b64decode(padded)
            if to_text:
                try:
                    decoded_text = decoded_bytes.decode("utf-8")
                    if is_mostly_printable(decoded_bytes):
                        return True, decoded_text, "Decoded URL-safe Base64 to UTF-8 text"
                except UnicodeDecodeError:
                    pass
            return True, decoded_bytes, "Decoded URL-safe Base64 to bytes"
        except Exception as e:
            return False, data, f"Base64 decoding failed: {e}"

    def confidence(self, data: Any, result: Any) -> Confidence:
        if isinstance(result, str):
            return Confidence.certain("Decoded valid Base64 string to readable text", TransformationCategory.RECOVERED)
        elif isinstance(result, bytes) and is_mostly_printable(result):
            return Confidence.high("Decoded Base64 to printable bytes", TransformationCategory.RECOVERED)
        elif isinstance(result, bytes):
            return Confidence.medium("Decoded Base64 to binary bytes", TransformationCategory.RECOVERED)
        return Confidence.unknown("Base64 decoding result indeterminate", TransformationCategory.UNRESOLVED)
