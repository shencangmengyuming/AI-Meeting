import base64
import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import uuid4

from websockets.asyncio.client import connect


class XunfeiAsrConnectionFactory:
    def __init__(
        self,
        app_id: str,
        api_key: str,
        api_secret: str,
        *,
        host: str = "office-api-ast-dx.iflyaisol.com",
        path: str = "/ast/communicate/v1",
    ) -> None:
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.host = host
        self.path = path

    def signed_url(
        self,
        *,
        utc: str | None = None,
        request_uuid: str | None = None,
    ) -> str:
        resolved_utc = utc or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        )
        session_id = (request_uuid or uuid4().hex).replace("-", "")
        parameters = {
            "appId": self.app_id,
            "accessKeyId": self.api_key,
            "audio_encode": "pcm_s16le",
            "lang": "autodialect",
            "samplerate": "16000",
            "sessionId": session_id,
            "utc": resolved_utc,
            "uuid": session_id,
        }
        canonical = urlencode(sorted(parameters.items()))
        signature = base64.b64encode(
            hmac.new(self.api_secret, canonical.encode(), hashlib.sha1).digest()
        ).decode()
        parameters["signature"] = signature
        query = urlencode(sorted(parameters.items()))
        return f"wss://{self.host}{self.path}?{query}"

    async def connect(self):
        return await connect(
            self.signed_url(),
            open_timeout=10,
            ping_interval=15,
            ping_timeout=10,
            close_timeout=5,
            max_queue=16,
        )
