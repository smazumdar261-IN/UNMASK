# Sample file containing string obfuscation patterns:
# - chr() chains
# - "".join() on char lists
# - bytes([..]).decode()
# - formatted strings

def extract_payload():
    protocol = "".join([chr(104), chr(116), chr(116), chr(112), chr(115)])
    domain = bytes([97, 112, 105, 46, 115, 101, 114, 118, 101, 114, 46, 110, 101, 116]).decode("utf-8")
    path = "/{}/{}".format("v1", "telemetry")
    endpoint = f"{protocol}://{domain}{path}"
    return endpoint


if __name__ == "__main__":
    url = extract_payload()
    print(url)
