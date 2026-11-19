import asyncio
import json
import time
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth_user.infrastructure.redis_session import RedisSessionAdapter
from app.auth_user.infrastructure.user_identity import MySqlAuthIdentityLookup
from app.media.application.audio_session import AudioSession
from app.media.application.connection_registry import ConnectionRegistry
from app.media.domain.transcription import TranscriptionUpdate
from app.media.infrastructure.asr import XunfeiAsrProvider

router = APIRouter()


def _registry(websocket: WebSocket) -> ConnectionRegistry:
    registry = getattr(websocket.app.state, "media_connections", None)
    if registry is None:
        registry = ConnectionRegistry()
        websocket.app.state.media_connections = registry
    return registry


@router.websocket("/api/xunzhi/v1/xunfei/audio-to-text/{user_id}")
async def audio_to_text(websocket: WebSocket, user_id: str) -> None:
    token = (
        websocket.query_params.get("token")
        or websocket.query_params.get("access_token")
        or websocket.query_params.get("satoken")
    )
    if not token:
        await websocket.close(code=4401)
        return
    resources = websocket.app.state.resources
    identity = MySqlAuthIdentityLookup(resources.session_factory, resources.redis)
    principal = await RedisSessionAdapter(resources.redis, identity).resolve(token)
    if principal is None or user_id not in {str(principal.user_id), principal.username}:
        await websocket.close(code=4403)
        return

    connection_id = str(uuid4())
    registry = _registry(websocket)
    push_service = getattr(websocket.app.state, "websocket_push_service", None)
    routing = getattr(push_service, "routing", None)
    audio = AudioSession(connection_id, str(principal.user_id))
    await websocket.accept()
    await registry.add(str(principal.user_id), connection_id, websocket)
    if routing is not None:
        await routing.register(str(principal.user_id))
    await websocket.send_json(
        {
            "type": "connected",
            "message": "WebSocket connected",
            "data": str(principal.user_id),
            "connectionId": connection_id,
        }
    )
    asr_task: asyncio.Task[None] | None = None
    routing_heartbeat: asyncio.Task[None] | None = None
    if routing is not None:
        async def refresh_routing() -> None:
            interval = max(float(getattr(routing, "ttl_seconds", 60)) / 3, 1)
            while True:
                await asyncio.sleep(interval)
                await routing.register(str(principal.user_id))

        routing_heartbeat = asyncio.create_task(
            refresh_routing(), name=f"media-routing-{connection_id}"
        )
    factory = getattr(websocket.app.state, "asr_connection_factory", None)
    if factory is not None:
        async def sink(update):
            await websocket.send_json(_transcription_payload(update))

        stop_event = asyncio.Event()

        async def run_asr() -> None:
            try:
                await XunfeiAsrProvider(factory.connect).run(
                    audio.queue,
                    sink,
                    stop_event,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "ASR_PROVIDER_ERROR",
                            "message": "Real-time transcription failed",
                        }
                    )
                except Exception:
                    pass

        asr_task = asyncio.create_task(run_asr(), name=f"asr-{connection_id}")
    try:
        while True:
            message = await websocket.receive()
            if message.get("bytes") is not None:
                try:
                    await audio.push(message["bytes"])
                except asyncio.QueueFull:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "AUDIO_BACKPRESSURE",
                            "message": "Audio buffer is full",
                        }
                    )
                continue
            command = _control_type(str(message.get("text") or ""))
            if command in {"stop", "end", "stop_transcription"}:
                await audio.stop()
                await websocket.send_json(
                    {
                        "type": "transcription_stopped",
                        "message": "Transcription stopped",
                    }
                )
                break
            if command == "start_transcription":
                await websocket.send_json(
                    {
                        "type": "transcription_started",
                        "message": "Transcription started",
                    }
                )
                continue
            if command in {"ping", "heartbeat"}:
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await audio.stop()
        if asr_task is not None:
            try:
                await asyncio.wait_for(asr_task, timeout=5)
            except (TimeoutError, ExceptionGroup):
                asr_task.cancel()
                await asyncio.gather(asr_task, return_exceptions=True)
        if routing_heartbeat is not None:
            routing_heartbeat.cancel()
            await asyncio.gather(routing_heartbeat, return_exceptions=True)
        await registry.remove(str(principal.user_id), connection_id)
        if routing is not None and not await registry.is_online(
            str(principal.user_id)
        ):
            await routing.unregister(str(principal.user_id))


def _control_type(raw: str) -> str:
    normalized = raw.strip().lower()
    if not normalized:
        return ""
    try:
        message = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    if isinstance(message, dict):
        return str(message.get("type") or "").strip().lower()
    return normalized


def _transcription_payload(update: TranscriptionUpdate) -> dict[str, object]:
    is_final = bool(update.final)
    payload: dict[str, object] = {
        "type": "final" if is_final else "transcription",
        "message": "Transcription completed" if is_final else "Partial snapshot",
        "data": update.full_text,
        "fullText": update.full_text,
        "displayText": update.display_text or update.full_text,
        "committedText": update.committed_text,
        "liveText": update.live_text,
        "revision": update.revision,
        "isSnapshot": True,
        "updateAction": "archive" if is_final else "replace",
        "timestamp": int(time.time() * 1000),
        "segmentId": update.segment_id,
        "sentenceSeq": update.segment_id,
        "segmentText": update.segment_text,
        "isFinalPacket": is_final,
    }
    if update.pgs is not None:
        payload["pgs"] = update.pgs
    if update.rg is not None:
        payload["rg"] = list(update.rg)
    if update.bg is not None:
        payload["bg"] = update.bg
    if update.ed is not None:
        payload["ed"] = update.ed
    return payload
