from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StreamEvent:
    kind: str
    data: str | None


class AgentProvider(Protocol):
    async def complete(
        self, prompt: str, *, stream: bool = False
    ) -> Any: ...
