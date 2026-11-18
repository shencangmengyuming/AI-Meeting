# Real-time Media Contract

Planned package boundary: `app/media/`.

ASR should be split into:

1. A transport adapter that receives audio and emits structured updates.
2. A session context that owns bounded buffering, task state, stop intent, and
   the last structured update.
3. A provider port and provider-specific adapter.
4. A deterministic transcription assembler independent of sockets.

The assembler must distinguish full snapshot, committed prefix, and live tail.
Provider final signals become internal segment stability; they are not exposed
as provider-specific state throughout the domain.

TTS task creation and task status/result retrieval are separate lifecycles.
All protocol compatibility tests and captured fixtures live under
repo-path: `tests/contracts`.
