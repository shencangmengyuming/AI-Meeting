from app.media.infrastructure.tts import TtsSigner


def test_tts_signer_returns_deterministic_authorization_header() -> None:
    signer = TtsSigner("api-key", "api-secret")

    signed = signer.sign("POST", "/v1/task", "Wed, 19 Nov 2026 00:00:00 GMT")

    assert signed.startswith("api_key=api-key, algorithm=hmac-sha256, headers=")
    assert "signature=" in signed
