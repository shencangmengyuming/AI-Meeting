---
name: xunzhi-media-domain
description: Use when implementing or reviewing Python real-time ASR, transcription assembly, media WebSockets, notifications, heartbeats, or TTS lifecycle behavior.
---

# Media Domain

The media core includes AST assembly, bounded audio queues, long-text TTS,
authenticated WebSocket lifecycle, ASR sender/receiver tasks, management push
and Redis ownership routing. Read
`references/realtime-media.md` before changing provider or routing semantics.
See `docs/reviews/python-media-review.md` for the current load and failure-drill
boundary.

## Constraints

- Authenticate a WebSocket before creating media session state.
- Separate WebSocket connection identity from business `session_id`.
- Keep provider protocols behind adapters.
- Bound buffers and define backpressure or overload behavior.
- Preserve transcription ordering, correction, finalization, and snapshot
  semantics with deterministic tests.
- Close streams, tasks, sockets, and provider clients on every terminal path.

## Current Entry Points

- `app/media/domain/transcription.py`
- `app/media/application/audio_session.py`
- `app/media/infrastructure/tts.py`
- `app/media/infrastructure/xunfei_tts.py`
- `app/media/application/connection_registry.py`
- `app/media/api/websocket.py`
- `app/media/infrastructure/websocket_routing.py`
- `app/media/infrastructure/asr.py`
- `app/media/application/push_service.py`
- `app/media/api/management.py`
- `app/media/api/router.py`
- `tests/media/`
