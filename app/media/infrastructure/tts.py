import base64
import hashlib
import hmac


class TtsSigner:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")

    def sign(self, method: str, path: str, date: str) -> str:
        signature_origin = (
            f"host: api.xf-yun.com\ndate: {date}\n"
            f"{method.upper()} {path} HTTP/1.1"
        )
        digest = hmac.new(
            self.api_secret,
            signature_origin.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(digest).decode("ascii")
        return (
            f"api_key={self.api_key}, algorithm=hmac-sha256, "
            f"headers=host date request-line, signature={signature}"
        )
