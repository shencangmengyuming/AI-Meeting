import json
from pathlib import Path
from typing import Any


def test_java_satoken_fixture_captures_redacted_runtime_contract() -> None:
    fixture_path = (
        Path(__file__).parent / "fixtures" / "auth" / "java_satoken.json"
    )
    fixture: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["fixtureVersion"] == 1
    assert fixture["configuration"] == {
        "tokenName": "Authorization",
        "tokenPrefix": "Bearer",
        "tokenStyle": "uuid",
        "timeoutSeconds": 2592000,
        "concurrent": True,
        "sharedToken": True,
    }
    assert fixture["http"]["login"]["data"]["token"] == "<redacted>"
    assert fixture["redis"]["token"]["keyTemplate"] == (
        "Authorization:login:token:{token}"
    )
    assert fixture["redis"]["session"]["keyTemplate"] == (
        "Authorization:login:session:{username}"
    )
    assert fixture["observations"]["secondLoginReturnsSameToken"] is True
    assert fixture["observations"]["pythonSessionReadByJava"] is True
    assert fixture["http"]["logout"]["deletesLegacyLoginHash"] is False
    serialized = json.dumps(fixture)
    assert "123456" not in serialized
    assert "7da1da84-d800-479f-a543-347a3dc8be2c" not in serialized
