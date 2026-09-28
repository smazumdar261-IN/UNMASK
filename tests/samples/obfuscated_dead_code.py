# Obfuscated sample featuring opaque predicates, dead stores, and unreachable code

def run_process():
    # Dead store (pure computation never read)
    dummy_key = 100 * 50 + 25

    # Opaque predicate (always true)
    if 2 + 2 == 4:
        status = "authorized"
    else:
        status = "blocked_by_trap"
        dummy_fail = 999

    return status

    # Unreachable code after return
    print("This code should never execute")
    exit(1)


if __name__ == "__main__":
    res = run_process()
    print("Status:", res)
