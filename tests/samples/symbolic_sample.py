"""Sample demonstrating Phase 4: Symbolic evaluation, reaching definitions, and type hints."""

def compute_secret(key_seed=1337):
    # Section 10 example: chained definitions with constant expressions
    x = 10
    y = x * 2
    z = y + 5

    # Obfuscated XOR chain: (k ^ 57005) ^ 57005 cancels to k
    magic_key = (key_seed ^ 57005) ^ 57005

    # Self-canceling offset
    offset = (z + 100) - z

    return magic_key + offset


if __name__ == "__main__":
    result = compute_secret()
    print("Secret computed:", result)
