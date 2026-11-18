import argparse
import base64
import copy
import json
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

REDACTED = "<redacted>"
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "apiKey",
    "apiSecret",
    "token",
    "access_token",
    "signedUrl",
}


def redact_fixture(value: Any, key: str | None = None) -> Any:
    if key is not None and (
        key in SENSITIVE_KEYS or key.lower() in SENSITIVE_KEYS
    ):
        return REDACTED
    if key == "files":
        return {name: REDACTED for name in value}
    if isinstance(value, dict):
        return {name: redact_fixture(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_fixture(item) for item in value]
    return value


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be a JSON object")
    required = {"fixtureVersion", "endpoint", "request", "response"}
    missing = required - fixture.keys()
    if missing:
        raise ValueError(f"fixture missing fields: {sorted(missing)}")
    response = fixture["response"]
    if not isinstance(response, dict) or not {
        "status", "headers", "body"
    }.issubset(response):
        raise ValueError("HTTP response requires status, headers and body")
    base64.b64decode(response["body"], validate=True)
    return fixture


async def record_http(base_url: str, scenario: dict[str, Any]) -> dict[str, Any]:
    method = str(scenario.get("method", "GET")).upper()
    path = str(scenario["path"])
    headers = dict(scenario.get("headers", {}))
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=False) as client:
        response = await client.request(
            method,
            path,
            headers=headers,
            params=scenario.get("params"),
            json=scenario.get("json"),
        )
    return {
        "fixtureVersion": 1,
        "endpoint": f"{method} {path}",
        "request": redact_fixture(
            {
                "headers": headers,
                "params": scenario.get("params"),
                "json": scenario.get("json"),
            }
        ),
        "response": {
            "status": response.status_code,
            "headers": redact_fixture(dict(response.headers)),
            "body": base64.b64encode(response.content).decode("ascii"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token-env")
    parser.add_argument("--scenario-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    scenarios = yaml.safe_load(args.scenario_file.read_text(encoding="utf-8"))
    if args.token_env:
        token = os.environ.get(args.token_env)
        if token:
            for scenario in scenarios:
                scenario.setdefault("headers", {})["Authorization"] = token
    args.output.mkdir(parents=True, exist_ok=True)
    for index, scenario in enumerate(scenarios, start=1):
        fixture = await record_http(args.base_url, copy.deepcopy(scenario))
        path = args.output / f"{index:03d}.json"
        path.write_text(
            json.dumps(redact_fixture(fixture), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
