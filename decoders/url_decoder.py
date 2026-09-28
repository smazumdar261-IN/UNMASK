"""URL percentage-encoding decoder plugin.

Per Section 7 of the Master Specification:
- Decodes percent-encoded URL strings (%XX, %uXXXX).
"""

import re
import urllib.parse
from typing import Any, Tuple

from core.confidence import Confidence, TransformationCategory
from decoders.registry import BaseDecoder

URL_ENCODED_RE = re.compile(r"%[0-9a-fA-F]{2}")


class URLDecoder(BaseDecoder):
    """Decodes percent-encoded URL strings."""

    name = "URLDecoder"
    description = "Decodes percent-encoded characters (%XX) in strings."

    def can_decode(self, data: Any) -> bool:
        if not isinstance(data, str):
            return False
        return bool(URL_ENCODED_RE.search(data))

    def decode(self, data: Any) -> Tuple[bool, Any, str]:
        if not isinstance(data, str):
            return False, data, "Input must be string"

        if not self.can_decode(data):
            return False, data, "No percent-encoding detected"

        try:
            decoded = urllib.parse.unquote(data)
            if decoded != data:
                return True, decoded, "Decoded percent-encoded string"
            return False, data, "No changes after unquoting"
        except Exception as e:
            return False, data, f"URL unquoting failed: {e}"

    def confidence(self, data: Any, result: Any) -> Confidence:
        return Confidence.certain("Decoded percent-encoded characters", TransformationCategory.RECOVERED)
