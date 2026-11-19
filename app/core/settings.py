from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_MEETING_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "mysql+asyncmy://localhost/ai_meeting?charset=utf8mb4"
    mongo_url: str = "mongodb://localhost:27017"
    mongo_database: str = "ai_meeting"
    redis_url: str = "redis://localhost:6379/0"
    http_connect_timeout: float = 5.0
    http_read_timeout: float = 30.0
    http_write_timeout: float = 30.0
    http_pool_timeout: float = 5.0
    xunfei_tts_app_id: str | None = None
    xunfei_tts_api_key: str | None = None
    xunfei_tts_api_secret: str | None = None
    xunfei_asr_app_id: str | None = None
    xunfei_asr_api_key: str | None = None
    xunfei_asr_api_secret: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
