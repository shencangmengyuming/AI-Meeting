# Agent Module Boundary

Planned package boundary: `app/agent/`.

The domain owns:

- general Agent session lifecycle;
- user and assistant message history;
- file attachment metadata and access control;
- business-scene to Agent configuration resolution;
- transport-neutral streaming events.

It does not own interview question state, scoring, follow-up rules, ASR, or TTS.
Those capabilities may call shared AI runtime ports, but their business state
stays in the owning domain.

Migration begins with recorded contracts under repo-path: `tests/contracts`,
then one session lifecycle slice, then streaming and file workflows.
