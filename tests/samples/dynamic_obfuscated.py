"""Sample obfuscated Python file for Secure Dynamic Analysis (Phase 11).

Demonstrates an algorithmic XOR cipher routine that static evaluation alone
cannot easily resolve, requiring isolated sandboxed dynamic analysis.
"""

def xor_decrypt(ciphertext, key):
    out = []
    for i, c in enumerate(ciphertext):
        out.append(chr(ord(c) ^ (key + (i % 3))))
    return "".join(out)

secret_payload = xor_decrypt("y^\\OY\x7fOH^O_|KR@EJH\x18\x1b\x1e\x1c", 42)
print(secret_payload)
