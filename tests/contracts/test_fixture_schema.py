import base64
import json
from pathlib import Path

from tools.record_java_contracts import load_fixture, redact_fixture


def test_http_fixture_requires_version_endpoint_and_encoded_body(
    tmp_path: Path,
) -> None:
    fixture = {
        "fixtureVersion": 1,
        "endpoint": "GET /actuator/health",
        "request": {"headers": {"Authorization": "Bearer secret"}},
        "response": {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": base64.b64encode(b'{"status":"UP"}').decode(),
        },
    }
    path = tmp_path / "health.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    loaded = load_fixture(path)
    assert loaded["fixtureVersion"] == 1
    assert base64.b64decode(loaded["response"]["body"]) == b'{"status":"UP"}'


def test_redaction_removes_credentials_and_file_content() -> None:
    fixture = {
        "request": {
            "headers": {"Authorization": "Bearer secret", "Cookie": "satoken=x"},
            "json": {"password": "plain", "apiKey": "key"},
            "files": {"resume": "bytes"},
        },
        "response": {"headers": {"set-cookie": "satoken=x"}},
    }

    redacted = redact_fixture(fixture)
    assert redacted["request"]["headers"]["Authorization"] == "<redacted>"
    assert redacted["request"]["headers"]["Cookie"] == "<redacted>"
    assert redacted["request"]["json"]["password"] == "<redacted>"
    assert redacted["request"]["json"]["apiKey"] == "<redacted>"
    assert redacted["request"]["files"]["resume"] == "<redacted>"
