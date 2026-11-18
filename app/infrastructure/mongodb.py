from pymongo import AsyncMongoClient


def create_mongo_resources(
    mongo_url: str,
    database_name: str,
) -> tuple[AsyncMongoClient, object]:
    client = AsyncMongoClient(mongo_url)
    return client, client[database_name]
