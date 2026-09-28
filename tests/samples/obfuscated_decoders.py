# Obfuscated sample utilizing decoder calls: base64, hex, and url unquote

import base64
import binascii
import urllib.parse


def get_credentials():
    encoded_user = "YWRtaW4="
    encoded_token = "3466336338656139"
    encoded_endpoint = "https%3A%2F%2Fvault%2Elocal%2Flogin"

    username = base64.b64decode(encoded_user).decode("utf-8")
    token = binascii.unhexlify(encoded_token).decode("utf-8")
    endpoint = urllib.parse.unquote(encoded_endpoint)

    return username, token, endpoint


if __name__ == "__main__":
    u, t, e = get_credentials()
    print(u, t, e)
