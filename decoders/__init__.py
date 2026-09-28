"""Decoders package and global registry initialization."""

from decoders.registry import BaseDecoder, DecoderRegistry, decoder_registry
from decoders.base64_decoder import Base64Decoder
from decoders.hex_decoder import HexDecoder
from decoders.unicode_decoder import UnicodeDecoder
from decoders.url_decoder import URLDecoder
from decoders.xor_decoder import XorDecoder
from decoders.compression_decoder import CompressionDecoder

# Register built-in decoders in standard priority order
b64_decoder = Base64Decoder()
hex_decoder = HexDecoder()
unicode_decoder = UnicodeDecoder()
url_decoder = URLDecoder()
xor_decoder = XorDecoder()
compression_decoder = CompressionDecoder()

decoder_registry.register(b64_decoder)
decoder_registry.register(hex_decoder)
decoder_registry.register(unicode_decoder)
decoder_registry.register(url_decoder)
decoder_registry.register(xor_decoder)
decoder_registry.register(compression_decoder)

__all__ = [
    "BaseDecoder",
    "DecoderRegistry",
    "decoder_registry",
    "Base64Decoder",
    "HexDecoder",
    "UnicodeDecoder",
    "URLDecoder",
    "XorDecoder",
    "CompressionDecoder",
    "b64_decoder",
    "hex_decoder",
    "unicode_decoder",
    "url_decoder",
    "xor_decoder",
    "compression_decoder",
]
