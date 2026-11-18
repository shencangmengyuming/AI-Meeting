from app.core.result import failure, success


def test_success_contract() -> None:
    assert success({"x": 1}).model_dump(by_alias=True) == {
        "code": "0",
        "message": None,
        "data": {"x": 1},
        "requestId": None,
    }


def test_failure_contract() -> None:
    assert failure("A000001", "bad request").model_dump(by_alias=True) == {
        "code": "A000001",
        "message": "bad request",
        "data": None,
        "requestId": None,
    }
