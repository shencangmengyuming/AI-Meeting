import pytest

from app.configuration.application.service import ConfigurationService


class Repository:
    def __init__(self):
        self.rows = {
            1: {
                "id": 1,
                "name": "model",
                "apiKey": "abcdefgh",
                "apiSecret": "secret",
                "enabled": True,
            }
        }

    async def get(self, item_id):
        return self.rows.get(item_id)

    async def page(self, offset, limit):
        return list(self.rows.values())

    async def create(self, values):
        self.rows[2] = {"id": 2, **values}
        return 2

    async def update(self, values):
        self.rows[values["id"]].update(values)

    async def delete(self, item_id):
        self.rows.pop(item_id, None)


@pytest.mark.anyio
async def test_configuration_service_masks_credentials() -> None:
    service = ConfigurationService(Repository())
    result = await service.get(1)

    assert result["apiKey"] == "abcd****fgh"
    assert "apiSecret" not in result


@pytest.mark.anyio
async def test_configuration_service_crud() -> None:
    repository = Repository()
    service = ConfigurationService(repository)
    item_id = await service.create({"name": "new", "apiSecret": "s"})
    await service.update({"id": item_id, "name": "renamed"})
    await service.delete(item_id)
    assert await repository.get(item_id) is None
