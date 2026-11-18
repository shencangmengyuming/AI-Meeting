from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase


def create_mongo_resources(
    mongo_url: str,
    database_name: str,
) -> tuple[AsyncMongoClient, AsyncDatabase]:
    client = AsyncMongoClient(mongo_url)
    return client, client[database_name]
