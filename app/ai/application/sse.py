import json


def encode_ai_event(kind: str, content: str) -> str:
    data = json.dumps(
        {"type": kind, "content": content},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"data: {data}\n\n"
