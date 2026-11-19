# Python Media Review

Reviewed against the Java baseline and the Python implementation on 2026-11-19.

## Certified behavior

- ASR parsing preserves `pgs`, `rg`, `bg`, `ed` and final metadata into the transcription assembler.
- Audio sessions use bounded queues and emit structured backpressure/failure errors.
- Authenticated WebSocket connections register node ownership, refresh TTLs and clean stale owners when no subscriber receives a push.
- TTS supports the standard `/xunfei/tts` route and keeps the legacy alias for compatibility.
- Management endpoints preserve the Java naked-JSON contracts while session routes use the shared result envelope.

## Residual risks

- Load tests should be run with production-sized ASR frame rates and concurrent TTS polling.
- Cross-node delivery depends on Redis Pub/Sub availability; local delivery remains the fast path.

## Gate result

Run media provider, WebSocket lifecycle, queue/backpressure and cross-node routing tests, then execute a deployment failure drill.
