from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeView:
    session_id: str
    state: Mapping[str, Any]
    source: str
    confidence: str


@dataclass(frozen=True)
class SnapshotResult:
    version: int
    state: Mapping[str, Any]
    applied: bool
