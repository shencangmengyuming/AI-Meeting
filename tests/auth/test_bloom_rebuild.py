import pytest

from app.workers.rebuild_user_bloom import rebuild_user_bloom


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class Session:
    async def execute(self, statement, params):
        offset = params["offset"]
        rows = [("alice",), ("bob",)][offset : offset + params["limit"]]
        return Result(rows)


class Factory:
    def __call__(self):
        return Context(Session())


class Context:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        pass


class Redis:
    def __init__(self):
        self.commands = []

    async def execute_command(self, *args):
        self.commands.append(args)
        return 1

    async def delete(self, key):
        self.commands.append(("DEL", key))

    async def rename(self, source, target):
        self.commands.append(("RENAME", source, target))


@pytest.mark.anyio
async def test_bloom_rebuild_replaces_live_key_after_population() -> None:
    redis = Redis()
    stats = await rebuild_user_bloom(Factory(), redis, batch_size=1)

    assert stats.scanned == 2
    assert redis.commands[-1][0] == "RENAME"
    assert [command[0] for command in redis.commands].count("BF.ADD") == 2
