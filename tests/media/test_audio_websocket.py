from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth_user.domain.session import AuthPrincipal
from app.auth_user.infrastructure.redis_session import RedisSessionAdapter
from app.media.api.websocket import router
from app.media.application.connection_registry import ConnectionRegistry
from app.media.domain.transcription import TranscriptionUpdate


class Routing:
    def __init__(self) -> None:
        self.registered: list[str] = []
        self.unregistered: list[str] = []

    async def register(self, user_id: str) -> None:
        self.registered.append(user_id)

    async def unregister(self, user_id: str) -> None:
        self.unregistered.append(user_id)


class FailingFactory:
    async def connect(self):
        raise RuntimeError("supplier unavailable")


def test_audio_websocket_registers_routing_and_reports_asr_failure(monkeypatch) -> None:
    async def resolve(self, token):
        assert token == "token"
        return AuthPrincipal(7, "owner", token, frozenset({"user"}))

    monkeypatch.setattr(RedisSessionAdapter, "resolve", resolve)
    routing = Routing()
    app = FastAPI()
    app.include_router(router)
    app.state.resources = SimpleNamespace(session_factory=object(), redis=object())
    app.state.media_connections = ConnectionRegistry()
    app.state.websocket_push_service = SimpleNamespace(routing=routing)
    app.state.asr_connection_factory = FailingFactory()

    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/xunzhi/v1/xunfei/audio-to-text/7?token=token"
        ) as websocket:
            opened = websocket.receive_json()
            failure = websocket.receive_json()
            websocket.send_text("stop")
            stopped = websocket.receive_json()

            assert opened["type"] == "connected"
            assert failure == {
                "type": "error",
                "code": "ASR_PROVIDER_ERROR",
                "message": "Real-time transcription failed",
            }
            assert stopped == {
                "type": "transcription_stopped",
                "message": "Transcription stopped",
            }

    assert routing.registered == ["7"]
    assert routing.unregistered == ["7"]
    assert app.state.media_connections._connections == {}


def test_transcription_payload_matches_java_frontend_contract() -> None:
    from app.media.api.websocket import _transcription_payload

    update = TranscriptionUpdate(
        full_text="你好",
        committed_text="",
        live_text="你好",
        revision=3,
        final=False,
        display_text="你好",
        segment_id=1,
        segment_text="你好",
    )

    payload = _transcription_payload(update)
    assert payload["type"] == "transcription"
    assert payload["data"] == "你好"
    assert payload["fullText"] == "你好"
    assert payload["updateAction"] == "replace"
    assert payload["isFinalPacket"] is False


def test_control_message_accepts_frontend_json_command() -> None:
    from app.media.api.websocket import _control_type

    assert _control_type('{"type":"stop_transcription"}') == "stop_transcription"
    assert _control_type("stop") == "stop"
