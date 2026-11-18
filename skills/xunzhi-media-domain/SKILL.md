---
name: xunzhi-media-domain
description: Use when implementing or reviewing Python real-time ASR, transcription assembly, media WebSockets, notifications, heartbeats, or TTS lifecycle behavior.
---

# Media Domain

This domain is not implemented yet. Read `references/realtime-media.md` before
adding media transports or provider adapters.

## Constraints

- Authenticate a WebSocket before creating media session state.
- Separate WebSocket connection identity from business `session_id`.
- Keep provider protocols behind adapters.
- Bound buffers and define backpressure or overload behavior.
- Preserve transcription ordering, correction, finalization, and snapshot
  semantics with deterministic tests.
- Close streams, tasks, sockets, and provider clients on every terminal path.
