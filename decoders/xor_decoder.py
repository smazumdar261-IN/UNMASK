"""XOR decoder plugin.

Per Section 17 of the Master Specification:
- Decodes single-byte and repeating-key XOR obfuscated data.
"""

from typing import Any, Optional, Tuple

from core.confidence import Confidence, TransformationCategory
from decoders.base64_decoder import is_mostly_printable
from decoders.registry import BaseDecoder


def apply_xor(data: bytes, key: bytes) -> bytes:
    """Apply repeating-key XOR operation."""
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


class XorDecoder(BaseDecoder):
    """Decodes XOR-obfuscated byte strings."""

    name = "XorDecoder"
    description = "Decodes single-byte or repeating-key XOR obfuscation."

    def can_decode(self, data: Any) -> bool:
        # Without a key, can_decode requires tuple of (data, key) or raw bytes
        if isinstance(data, tuple) and len(data) == 2:
            d, k = data
            return isinstance(d, (bytes, str, list)) and isinstance(k, (int, bytes, str, list))
        return False

    def decode(self, data: Any, key: Optional[Any] = None) -> Tuple[bool, Any, str]:
        if isinstance(data, tuple) and len(data) == 2:
            data, key = data

        if key is None:
            return False, data, "XOR decoding requires a key"

        # Normalize data to bytes
        raw_data: bytes
        if isinstance(data, str):
            raw_data = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            raw_data = bytes(data)
        elif isinstance(data, (list, tuple)) and all(isinstance(x, int) for x in data):
            raw_data = bytes(data)
        else:
            return False, data, "Data must be bytes or string"

        # Normalize key to bytes
        raw_key: bytes
        if isinstance(key, int):
            raw_key = bytes([key & 0xFF])
        elif isinstance(key, str):
            raw_key = key.encode("utf-8")
        elif isinstance(key, (bytes, bytearray)):
            raw_key = bytes(key)
        elif isinstance(key, (list, tuple)) and all(isinstance(x, int) for x in key):
            raw_key = bytes(key)
        else:
            return False, data, "Key must be int, bytes, or string"

        try:
            result_bytes = apply_xor(raw_data, raw_key)
            try:
                result_text = result_bytes.decode("utf-8")
                if is_mostly_printable(result_bytes):
                    return True, result_text, f"XOR decoded with {len(raw_key)}-byte key to readable UTF-8"
            except UnicodeDecodeError:
                pass
            return True, result_bytes, f"XOR decoded with {len(raw_key)}-byte key to bytes"
        except Exception as e:
            return False, data, f"XOR decoding failed: {e}"

    def confidence(self, data: Any, result: Any) -> Confidence:
        if isinstance(result, str):
            return Confidence.certain("XOR decoded to readable string", TransformationCategory.RECOVERED)
        elif isinstance(result, bytes) and is_mostly_printable(result):
            return Confidence.high("XOR decoded to printable bytes", TransformationCategory.RECOVERED)
        return Confidence.medium("XOR decoded to binary bytes", TransformationCategory.RECOVERED)
