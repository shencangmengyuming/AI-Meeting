from app.media.infrastructure.xunfei_asr_client import XunfeiAsrConnectionFactory


def test_xunfei_asr_signed_url_contains_required_credentials() -> None:
    factory = XunfeiAsrConnectionFactory("app-id", "api-key", "api-secret")

    url = factory.signed_url(
        utc="2026-11-19T10:00:00+0000",
        request_uuid="fixed-uuid",
    )

    assert url.startswith(
        "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1?"
    )
    assert "appId=app-id" in url
    assert "accessKeyId=api-key" in url
    assert "sessionId=" in url
    assert "signature=" in url
