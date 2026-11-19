from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSession:
    session_id: str
    user_id: int
    title: str
    agent_id: int | None = None
