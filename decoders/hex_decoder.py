"""Hexadecimal decoder plugin.

Per Section 7 & Section 17 of the Master Specification:
- Decodes hexadecimal string representations.
- Supports formats: "48656c6c6f", "0x48656c6c6f", "48 65 6c", "\\x48\\x65".
- Decodes into readable text or bytes.
"""

import binascii
import re
from typing import Any, Tuple

from core.confidence import Confidence, TransformationCategory
from decoders.base64_decoder import is_mostly_printable
from decoders.registry import BaseDecoder

HEX_PURE_RE = re.compile(r"^[0-9a-fA-F]+$")
HEX_ESCAPE_RE = re.compile(r"^(?:\\x[0-9a-fA-F]{2})+$")


class HexDecoder(BaseDecoder):
    """Decodes hexadecimal encoded data."""

    name = "HexDecoder"
    description = "Decodes hexadecimal strings into text or bytes."

    def _clean_input(self, data: Any) -> Tuple[bool, str]:
        if not isinstance(data, (str, bytes)):
            return False, ""

        text = data.decode("ascii", errors="ignore") if isinstance(data, bytes) else data
        text = text.strip()

        if text.startswith("0x") or text.startswith("0X"):
            text = text[2:]

        # Handle \x escapes
        if "\\x" in text:
            if HEX_ESCAPE_RE.match(text):
                text = text.replace("\\x", "")
            else:
                return False, ""

        # Remove spaces or colons if used as byte separators (e.g. "48 65 6c")
        if " " in text or ":" in text:
            cleaned = text.replace(" ", "").replace(":", "")
            if len(cleaned) % 2 == 0 and HEX_PURE_RE.match(cleaned):
                text = cleaned

        if len(text) < 4 or len(text) % 2 != 0:
            return False, ""

        if not HEX_PURE_RE.match(text):
            return False, ""

        return True, text

    def can_decode(self, data: Any) -> bool:
        valid, clean = self._clean_input(data)
        if not valid:
            return False
        try:
            decoded = bytes.fromhex(clean)
            return len(decoded) > 0
        except Exception:
            return False

    def decode(self, data: Any, to_text: bool = False) -> Tuple[bool, Any, str]:
        valid, clean = self._clean_input(data)
        if not valid:
            return False, data, "Invalid hexadecimal format"

        try:
            decoded_bytes = bytes.fromhex(clean)
            if to_text:
                try:
                    decoded_text = decoded_bytes.decode("utf-8")
                    if is_mostly_printable(decoded_bytes):
                        return True, decoded_text, f"Decoded {len(clean)//2} hex bytes to readable UTF-8"
                except UnicodeDecodeError:
                    pass
            return True, decoded_bytes, f"Decoded {len(clean)//2} hex bytes"
        except Exception as e:
            return False, data, f"Hex decoding failed: {e}"

    def confidence(self, data: Any, result: Any) -> Confidence:
        if isinstance(result, str):
            return Confidence.certain("Decoded hexadecimal to readable string", TransformationCategory.RECOVERED)
        elif isinstance(result, bytes) and is_mostly_printable(result):
            return Confidence.high("Decoded hexadecimal to printable bytes", TransformationCategory.RECOVERED)
        elif isinstance(result, bytes):
            return Confidence.medium("Decoded hexadecimal to raw bytes", TransformationCategory.RECOVERED)
        return Confidence.unknown("Hexadecimal decoding result indeterminate", TransformationCategory.UNRESOLVED)
