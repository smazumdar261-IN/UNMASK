"""Unit tests for Decoder Plugins and Registry (Phase 1D)."""

import base64
import gzip
import unittest
import zlib

from decoders import (
    Base64Decoder,
    CompressionDecoder,
    DecoderRegistry,
    HexDecoder,
    UnicodeDecoder,
    URLDecoder,
    XorDecoder,
    decoder_registry,
)


class TestDecoders(unittest.TestCase):
    """Test suite for individual decoder plugins and registry."""

    def test_base64_decoder(self) -> None:
        dec = Base64Decoder()
        self.assertTrue(dec.can_decode("SGVsbG8gV29ybGQ="))
        self.assertTrue(dec.can_decode(b"SGVsbG8gV29ybGQ="))
        self.assertFalse(dec.can_decode("no!"))
        self.assertFalse(dec.can_decode("abc"))  # too short
        self.assertFalse(dec.can_decode(12345))

        success, res, _ = dec.decode("SGVsbG8gV29ybGQ=")
        self.assertTrue(success)
        self.assertEqual(res, b"Hello World")

        success, res_txt, _ = dec.decode("SGVsbG8gV29ybGQ=", to_text=True)
        self.assertTrue(success)
        self.assertEqual(res_txt, "Hello World")

        conf = dec.confidence("SGVsbG8gV29ybGQ=", res_txt)
        self.assertEqual(conf.level.value, "CERTAIN")

    def test_base64_urlsafe(self) -> None:
        dec = Base64Decoder()
        raw = b"data\xfb\xfftest"
        encoded = base64.urlsafe_b64encode(raw).decode()
        self.assertTrue(dec.can_decode(encoded))
        success, res, _ = dec.decode(encoded)
        self.assertTrue(success)
        self.assertEqual(res, raw)

    def test_hex_decoder(self) -> None:
        dec = HexDecoder()
        self.assertTrue(dec.can_decode("48656c6c6f"))
        self.assertTrue(dec.can_decode("0x48656c6c6f"))
        self.assertTrue(dec.can_decode("48 65 6c 6c 6f"))
        self.assertTrue(dec.can_decode(r"\x48\x65\x6c\x6c\x6f"))
        self.assertFalse(dec.can_decode("486"))  # Odd length
        self.assertFalse(dec.can_decode("ZZZZ"))  # Invalid hex

        success, res, _ = dec.decode("48656c6c6f")
        self.assertTrue(success)
        self.assertEqual(res, b"Hello")

        success, res_txt, _ = dec.decode("48656c6c6f", to_text=True)
        self.assertTrue(success)
        self.assertEqual(res_txt, "Hello")

    def test_unicode_decoder(self) -> None:
        dec = UnicodeDecoder()
        raw_esc = r"\u0048\u0065\u006c\u006c\u006f"
        self.assertTrue(dec.can_decode(raw_esc))
        success, res, _ = dec.decode(raw_esc)
        self.assertTrue(success)
        self.assertEqual(res, "Hello")

    def test_url_decoder(self) -> None:
        dec = URLDecoder()
        url_enc = "admin%40domain%2Ecom%20login"
        self.assertTrue(dec.can_decode(url_enc))
        success, res, _ = dec.decode(url_enc)
        self.assertTrue(success)
        self.assertEqual(res, "admin@domain.com login")

    def test_xor_decoder(self) -> None:
        dec = XorDecoder()
        plaintext = b"SECRET_KEY"
        key = 0x42
        ciphertext = bytes([b ^ key for b in plaintext])

        self.assertTrue(dec.can_decode((ciphertext, key)))
        success, res, _ = dec.decode((ciphertext, key))
        self.assertTrue(success)
        self.assertEqual(res, "SECRET_KEY")

        # Multi-byte key
        mb_key = b"KEY"
        mb_cipher = bytes([b ^ mb_key[i % len(mb_key)] for i, b in enumerate(plaintext)])
        success, res, _ = dec.decode((mb_cipher, mb_key))
        self.assertTrue(success)
        self.assertEqual(res, "SECRET_KEY")

    def test_compression_decoder(self) -> None:
        dec = CompressionDecoder()
        original = b"Payload with compression"
        zlib_compressed = zlib.compress(original)
        gzip_compressed = gzip.compress(original)

        self.assertTrue(dec.can_decode(zlib_compressed))
        success, res, _ = dec.decode(zlib_compressed)
        self.assertTrue(success)
        self.assertEqual(res, "Payload with compression")

        self.assertTrue(dec.can_decode(gzip_compressed))
        success, res, _ = dec.decode(gzip_compressed)
        self.assertTrue(success)
        self.assertEqual(res, "Payload with compression")

    def test_decoder_registry(self) -> None:
        self.assertIsNotNone(decoder_registry.get("base64decoder"))
        self.assertIsNotNone(decoder_registry.get("hexdecoder"))
        self.assertIsNotNone(decoder_registry.get("unicodedecoder"))
        self.assertIsNotNone(decoder_registry.get("urldecoder"))
        self.assertIsNotNone(decoder_registry.get("xordecoder"))
        self.assertIsNotNone(decoder_registry.get("compressiondecoder"))

        # Find matching decoders
        matches = decoder_registry.find_matching_decoders("SGVsbG8gV29ybGQ=")
        self.assertTrue(any(isinstance(m, Base64Decoder) for m in matches))


if __name__ == "__main__":
    unittest.main()
