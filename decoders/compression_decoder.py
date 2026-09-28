"""Compression decoder plugin.

Per Section 5 of the Master Specification:
- Decodes zlib, gzip, and bz2 compressed payloads when encountered.
"""

import gzip
import zlib
from typing import Any, Tuple

from core.confidence import Confidence, TransformationCategory
from decoders.base64_decoder import is_mostly_printable
from decoders.registry import BaseDecoder


class CompressionDecoder(BaseDecoder):
    """Decodes zlib, gzip, and bz2 compressed byte streams."""

    name = "CompressionDecoder"
    description = "Decompresses zlib, gzip, and bz2 payloads."

    def can_decode(self, data: Any) -> bool:
        if not isinstance(data, (bytes, bytearray)):
            return False
        b = bytes(data)
        # Check standard magic headers:
        # zlib: 0x78 0x9c, 0x78 0x01, 0x78 0xda
        # gzip: 0x1f 0x8b
        # bz2:  0x42 0x5a ('BZ')
        if len(b) >= 2:
            if b[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
                return True
            if b[:2] == b"\x1f\x8b":
                return True
            if b[:2] == b"BZ":
                return True
        return False

    def decode(self, data: Any) -> Tuple[bool, Any, str]:
        if not isinstance(data, (bytes, bytearray)):
            return False, data, "Input must be bytes"

        b = bytes(data)

        # Try zlib
        try:
            decomp = zlib.decompress(b)
            try:
                text = decomp.decode("utf-8")
                if is_mostly_printable(decomp):
                    return True, text, "Decompressed zlib payload to UTF-8 text"
            except UnicodeDecodeError:
                pass
            return True, decomp, "Decompressed zlib payload to bytes"
        except Exception:
            pass

        # Try gzip
        try:
            decomp = gzip.decompress(b)
            try:
                text = decomp.decode("utf-8")
                if is_mostly_printable(decomp):
                    return True, text, "Decompressed gzip payload to UTF-8 text"
            except UnicodeDecodeError:
                pass
            return True, decomp, "Decompressed gzip payload to bytes"
        except Exception:
            pass

        # Try bz2
        try:
            import bz2
            decomp = bz2.decompress(b)
            try:
                text = decomp.decode("utf-8")
                if is_mostly_printable(decomp):
                    return True, text, "Decompressed bz2 payload to UTF-8 text"
            except UnicodeDecodeError:
                pass
            return True, decomp, "Decompressed bz2 payload to bytes"
        except Exception as e:
            return False, data, f"Decompression failed: {e}"

    def confidence(self, data: Any, result: Any) -> Confidence:
        return Confidence.certain("Decompressed verified payload header", TransformationCategory.RECOVERED)
