import json
from collections.abc import Iterable, Iterator

from app.agent.domain.streaming import StreamEvent


class AgentStreamEncoder:
    def encode(self, events: Iterable[StreamEvent]) -> Iterator[str]:
        for event in events:
            payload = {} if event.data is None else event.data
            if not isinstance(payload, str):
                payload = json.dumps(payload, ensure_ascii=False)
            yield f"event: {event.kind}\ndata: {payload}\n\n"
