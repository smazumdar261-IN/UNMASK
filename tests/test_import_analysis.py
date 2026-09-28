"""Unit tests for ImportNormalizationPass (Phase 2)."""

import unittest

from core.provenance import ProvenanceTracker
from languages.python.parser import PythonParser
from passes.import_analysis import ImportNormalizationPass


class TestImportAnalysis(unittest.TestCase):
    """Test suite for normalizing aliased imports and callable pointers."""

    def setUp(self) -> None:
        self.parser = PythonParser()

    def normalize(self, code: str) -> str:
        tree = self.parser.parse(code)
        tracker = ProvenanceTracker()
        pass_instance = ImportNormalizationPass(filename="test.py")
        new_tree = pass_instance.run(tree, tracker)
        return self.parser.unparse(new_tree)

    def test_module_alias_normalization(self) -> None:
        code = "import base64 as _b\nres = _b.b64decode('SGVsbG8=')"
        out = self.normalize(code)
        self.assertIn("base64.b64decode('SGVsbG8=')", out)

    def test_from_import_alias_normalization(self) -> None:
        code = "from base64 import b64decode as _decode\nres = _decode('SGVsbG8=')"
        out = self.normalize(code)
        self.assertIn("base64.b64decode('SGVsbG8=')", out)

    def test_function_variable_pointer_normalization(self) -> None:
        code = "import binascii\nfn = binascii.unhexlify\nres = fn('48656c6c6f')"
        out = self.normalize(code)
        self.assertIn("binascii.unhexlify('48656c6c6f')", out)


if __name__ == "__main__":
    unittest.main()
