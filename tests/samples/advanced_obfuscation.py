# Advanced Python Obfuscation Sample:
# - Aliased imports
# - Multi-stage decoding (Hex -> Base64 -> String)
# - Wrapper function indirection
# - Opaque predicates and dead code
# - Algebraic identity noise (x + 0, x * 1, etc.)

import base64 as _b64
from binascii import unhexlify as _hex_decode


def _secret_wrapper(payload):
    # Wrapper function forwarding to decoded payload
    return _b64.b64decode(payload)


def unlock_system():
    # Multi-stage encoded token:
    # "MASTER_KEY_2026" in Base64 is "TUFTVEVSX0tFWV8yMDI2"
    # "TUFTVEVSX0tFWV8yMDI2" in Hex is "54554654564552535f544657595f794d4449794e673d3d"
    hex_stage = "54554654564552535f544657595f794d4449794e673d3d"

    # Dead store and identity noise
    decoy = 999 * 1 + 0 - 0

    if (100 * 2) > 50:
        stage1 = _hex_decode(hex_stage)
        stage2 = _secret_wrapper(stage1).decode("utf-8")
        status = stage2
    else:
        status = "INVALID_KEY"
        dummy_flag = 404

    return status


if __name__ == "__main__":
    result = unlock_system()
    print("Unlocked with:", result)
