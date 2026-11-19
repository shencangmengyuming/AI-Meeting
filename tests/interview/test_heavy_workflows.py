import pytest

from app.agent.domain.configuration import AgentConfiguration
from app.ai_runtime.application.singleflight import DistributedSingleFlight
from app.interview.application.ai_guard import AiCallGuard
from app.interview.application.heavy_workflows import (
    InterviewDemeanorService,
    InterviewExtractionService,
)


class Collection:
    def __init__(self, document=None):
        self.document = document
        self.inserted = []
        self.updates = []

    async def find_one(self, query, projection=None):
        return self.document

    async def insert_one(self, document):
        self.inserted.append(document)

    async def update_one(self, query, update, upsert=False):
        self.updates.append((query, update))
        matches = self.document is not None and all(
            self.document.get(key) == value
            for key, value in query.items()
            if not isinstance(value, dict)
        )
        if matches:
            if isinstance(self.document, dict):
                self.document.update(update.get("$set", {}))
        elif upsert:
            self.document = {
                **query,
                **update.get("$setOnInsert", {}),
                **update.get("$set", {}),
            }

        class Result:
            matched_count = 1

        return Result()


class Database:
    def __init__(self):
        self.collections = {
            "interview_session": Collection({"sessionId": "s1", "userId": 7}),
            "interview_question": Collection(),
        }
    def __getitem__(self, name):
        return self.collections[name]


class SnapshotCollection(Collection):
    async def replace_one(self, query, document, *, upsert):
        del query, upsert
        self.document = document
        return type("Result", (), {"matched_count": 1, "upserted_id": None})()


class Redis:
    def __init__(self):
        self.hashes = {}
        self.values = {}

    async def hset(self, key, mapping):
        self.hashes[key] = mapping

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


class Configurations:
    async def resolve(self, scene, aliases=()):
        return AgentConfiguration(1, scene, "key", "secret", "flow")

    async def resolve_by_id(self, agent_id):
        return AgentConfiguration(agent_id, "bound", "key", "secret", "flow")


class CapturingConfigurations(Configurations):
    def __init__(self) -> None:
        self.requests = []

    async def resolve(self, scene, aliases=()):
        self.requests.append((scene, aliases))
        return await super().resolve(scene, aliases)


class Uploader:
    async def upload(self, filename, content_type, content, configuration):
        return "https://xingchen-api.xf-yun.com/file"


class Workflow:
    def __init__(self):
        self.calls = 0

    async def invoke(self, configuration, prompt, file_url, session_id):
        self.calls += 1
        if "photo" in prompt.lower():
            return {
                "panicLevel": 7,
                "seriousnessLevel": 8,
                "emoticonHandling": 9,
                "compositeScore": 8,
            }
        return {
            "questions": ["Q1", "Q2"],
            "suggestions": ["S1"],
            "resumeScore": 86,
            "type": "backend",
        }


class CapturingWorkflow(Workflow):
    def __init__(self):
        super().__init__()
        self.prompt = None

    async def invoke(self, configuration, prompt, file_url, session_id):
        self.prompt = prompt
        return await super().invoke(configuration, prompt, file_url, session_id)


@pytest.mark.anyio
async def test_resume_extraction_persists_questions_and_score() -> None:
    database, redis = Database(), Redis()
    service = InterviewExtractionService(
        database, redis, Configurations(), Uploader(), Workflow()
    )

    result = await service.extract("s1", 7, "resume.pdf", "application/pdf", b"pdf")

    assert result["questions"] == ["Q1", "Q2"]
    assert result["resumeScore"] == 86
    assert redis.hashes["interview:questions:session:s1"] == {"1": "Q1", "2": "Q2"}
    session = database.collections["interview_session"].document
    assert session is not None
    assert session["status"] == "READY"


@pytest.mark.anyio
async def test_resume_extraction_requires_structured_workflow_output() -> None:
    workflow = CapturingWorkflow()
    service = InterviewExtractionService(
        Database(), Redis(), Configurations(), Uploader(), workflow
    )

    await service.extract("s1", 7, "resume.pdf", "application/pdf", b"pdf")

    assert workflow.prompt is not None
    for field in ("questions", "sugest", "type", "resumeScore"):
        assert field in workflow.prompt


@pytest.mark.anyio
async def test_demeanor_normalizes_ten_point_scale_to_hundred() -> None:
    database, redis = Database(), Redis()
    service = InterviewDemeanorService(
        database, redis, Configurations(), Uploader(), Workflow()
    )

    result = await service.evaluate("s1", 7, "photo.jpg", "image/jpeg", b"jpg")

    assert result["compositeScore"] == 80
    assert redis.values["interview:demeanor:score:s1"] == "80"
    assert redis.values["demeanor:panic:s1"] == "70"
    assert redis.values["demeanor:seriousness:s1"] == "80"
    assert redis.values["demeanor:emoticon:s1"] == "90"
    assert redis.values["demeanor:composite:s1"] == "80"


@pytest.mark.anyio
async def test_demeanor_prompt_requires_java_score_contract() -> None:
    workflow = CapturingWorkflow()
    service = InterviewDemeanorService(
        Database(), Redis(), Configurations(), Uploader(), workflow
    )

    await service.evaluate("s1", 7, "photo.jpg", "image/jpeg", b"jpg")

    assert workflow.prompt == (
        "Evaluate this photo and return integer scores (0-100) for "
        "panicLevel, seriousnessLevel, emoticonHandling and compositeScore."
    )


@pytest.mark.anyio
async def test_demeanor_refreshes_existing_runtime_snapshot() -> None:
    database, redis = Database(), Redis()
    snapshot = SnapshotCollection(
        {"sessionId": "s1", "version": 1, "status": "ASKING"}
    )
    database.collections["interview_runtime_snapshot"] = snapshot
    service = InterviewDemeanorService(
        database, redis, Configurations(), Uploader(), Workflow()
    )

    await service.evaluate("s1", 7, "photo.jpg", "image/jpeg", b"jpg")

    assert snapshot.document["version"] == 2
    assert snapshot.document["demeanorScore"] == 80
    assert snapshot.document["demeanorDetails"]["panicLevel"] == 70


@pytest.mark.anyio
async def test_resume_extraction_replays_singleflight_result() -> None:
    database, redis, workflow = Database(), Redis(), Workflow()
    service = InterviewExtractionService(
        database,
        redis,
        Configurations(),
        Uploader(),
        workflow,
        ai_guard=AiCallGuard(timeout_seconds=1),
        singleflight=DistributedSingleFlight(redis),
    )

    first = await service.extract("s1", 7, "resume.pdf", "application/pdf", b"pdf")
    second = await service.extract("s1", 7, "resume.pdf", "application/pdf", b"pdf")

    assert first == second
    assert workflow.calls == 1
    document = database.collections["interview_question"].document
    assert isinstance(document, dict)
    assert document["questions"] == [
        "Q1",
        "Q2",
    ]


@pytest.mark.anyio
async def test_resume_extraction_replaces_existing_session_question_document() -> None:
    database, redis = Database(), Redis()
    questions = database.collections["interview_question"]
    questions.document = {"sessionId": "s1", "questions": ["old"]}
    service = InterviewExtractionService(
        database, redis, Configurations(), Uploader(), Workflow()
    )

    await service.extract("s1", 7, "resume.pdf", "application/pdf", b"new-pdf")

    assert questions.document["questions"] == ["Q1", "Q2"]


@pytest.mark.anyio
async def test_heavy_workflows_resolve_java_agent_names() -> None:
    database, redis = Database(), Redis()
    configurations = CapturingConfigurations()
    extraction = InterviewExtractionService(
        database, redis, configurations, Uploader(), Workflow()
    )
    demeanor = InterviewDemeanorService(
        database, redis, configurations, Uploader(), Workflow()
    )

    await extraction.extract("s1", 7, "resume.pdf", "application/pdf", b"pdf")
    await demeanor.evaluate("s1", 7, "photo.jpg", "image/jpeg", b"jpg")

    assert "面试出题官" in configurations.requests[0][1]
    assert "神态分析官" in configurations.requests[1][1]
