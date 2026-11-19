from typing import Any, Protocol


class ConfigurationRepository(Protocol):
    async def get(self, item_id: int) -> dict[str, Any] | None: ...
    async def page(self, offset: int, limit: int) -> list[dict[str, Any]]: ...
    async def create(self, values: dict[str, Any]) -> int: ...
    async def update(self, values: dict[str, Any]) -> None: ...
    async def delete(self, item_id: int) -> None: ...


class ConfigurationService:
    def __init__(self, repository: ConfigurationRepository) -> None:
        self.repository = repository

    async def get(self, item_id: int) -> dict[str, Any]:
        row = await self.repository.get(item_id)
        if row is None:
            raise LookupError(f"configuration not found: {item_id}")
        return _public(row)

    async def page(self, current: int, size: int) -> dict[str, Any]:
        resolved_current = max(current, 1)
        resolved_size = min(max(size, 1), 100)
        rows = await self.repository.page(
            (resolved_current - 1) * resolved_size, resolved_size
        )
        return {
            "records": [_public(row) for row in rows],
            "current": resolved_current,
            "size": resolved_size,
        }

    async def create(self, values: dict[str, Any]) -> int:
        return await self.repository.create(values)

    async def update(self, values: dict[str, Any]) -> None:
        await self.repository.update(values)

    async def delete(self, item_id: int) -> None:
        await self.repository.delete(item_id)

    async def enabled(self) -> list[dict[str, Any]]:
        method = getattr(self.repository, "enabled")
        return [_public(row) for row in await method()]

    async def find_by(self, name: str, value: Any) -> dict[str, Any]:
        method = getattr(self.repository, "find_by")
        row = await method(name, value)
        if row is None:
            raise LookupError(f"configuration not found: {value}")
        return _public(row)

    async def toggle(self, item_id: int, enabled: int) -> None:
        method = getattr(self.repository, "toggle")
        await method(item_id, enabled)


def _public(row: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in row.items() if key != "apiSecret"}
    api_key = result.get("apiKey")
    if isinstance(api_key, str):
        result["apiKey"] = (
            "****" if len(api_key) <= 4 else f"{api_key[:4]}****{api_key[-3:]}"
        )
    return result
