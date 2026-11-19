import json

import pytest

from app.agent.application.files import AgentFileUploadService
from app.agent.domain.configuration import AgentConfiguration


class Configurations:
    def __init__(self):
        self.resolved_ids = []

    async def resolve(self, scene, aliases=()):
        return AgentConfiguration(7, "general", "key", "secret", "flow")

    async def resolve_by_id(self, agent_id):
        self.resolved_ids.append(agent_id)
        return AgentConfiguration(agent_id, "bound", "key", "secret", "flow")


class Sessions:
    async def bound_agent_id(self, session_id, user_id):
        assert (session_id, user_id) == ("s1", 3)
        return 42


class Uploader:
    async def upload(self, filename, content_type, content, configuration):
        return "https://xingchen-api.xf-yun.com/files/a.pdf"


class Repository:
    def __init__(self, fail=False):
        self.fail = fail
        self.saved = []

    async def save(self, asset):
        if self.fail:
            raise RuntimeError("mysql down")
        self.saved.append(asset)
        return 9


class Redis:
    def __init__(self): self.values = []
    async def lpush(self, key, value): self.values.append((key, value))


@pytest.mark.anyio
async def test_agent_file_upload_persists_remote_asset() -> None:
    repository = Repository()
    service = AgentFileUploadService(Configurations(), Uploader(), repository, Redis())

    result = await service.upload(
        username="owner",
        session_id=None,
        biz_type=None,
        filename="resume.pdf",
        content_type="application/pdf",
        content=b"pdf",
    )

    assert result["id"] == 9
    assert result["fileUrl"].startswith("https://xingchen-api.xf-yun.com/")
    assert repository.saved[0]["fileExt"] == "pdf"


@pytest.mark.anyio
async def test_agent_file_upload_queues_compensation_after_database_failure() -> None:
    redis = Redis()
    service = AgentFileUploadService(
        Configurations(), Uploader(), Repository(fail=True), redis
    )

    with pytest.raises(RuntimeError, match="mysql down"):
        await service.upload(
            username="owner",
            session_id=None,
            biz_type="resume",
            filename="resume.pdf",
            content_type="application/pdf",
            content=b"pdf",
        )

    payload = json.loads(redis.values[0][1])
    assert payload["asset"]["fileUrl"].startswith("https://xingchen-api.xf-yun.com/")
    assert payload["attempts"] == 0


@pytest.mark.anyio
async def test_agent_file_upload_uses_owned_session_bound_agent() -> None:
    configurations = Configurations()
    repository = Repository()
    service = AgentFileUploadService(
        configurations,
        Uploader(),
        repository,
        Redis(),
        sessions=Sessions(),
    )

    result = await service.upload(
        username="owner",
        user_id=3,
        session_id="s1",
        biz_type="resume",
        filename="resume.pdf",
        content_type="application/pdf",
        content=b"pdf",
    )

    assert configurations.resolved_ids == [42]
    assert repository.saved[0]["agentId"] == 42
    assert result["sessionId"] == "s1"
