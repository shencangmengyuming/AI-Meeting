import pytest
from testcontainers.core.container import DockerContainer

from app.infrastructure.mongodb import create_mongo_resources


@pytest.mark.integration
@pytest.mark.anyio
async def test_mongo_resource_supports_insert_read_delete() -> None:
    with DockerContainer("mongo:7").with_exposed_ports(27017) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(27017)
        client, database = create_mongo_resources(
            f"mongodb://{host}:{port}", "resource_probe"
        )
        try:
            collection = database["items"]
            await collection.insert_one({"name": "probe"})
            assert await collection.count_documents({"name": "probe"}) == 1
            await collection.delete_many({"name": "probe"})
            assert await collection.count_documents({"name": "probe"}) == 0
        finally:
            await client.close()
