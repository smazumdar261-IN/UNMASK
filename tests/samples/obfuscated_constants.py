# Sample obfuscated constant expressions and variable aliases

def compute():
    step1 = 100 * 2 + 50
    step2 = step1 // 5
    prefix = "USER_" + "KEY_"
    suffix = "2026"[::-1]
    token = prefix + suffix
    return step2, token


if __name__ == "__main__":
    val, tok = compute()
    print(val, tok)
