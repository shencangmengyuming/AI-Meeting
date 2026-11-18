from contextvars import ContextVar

request_trace_id: ContextVar[str | None] = ContextVar(
    "request_trace_id", default=None
)
