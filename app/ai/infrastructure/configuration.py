from typing import Any

from sqlalchemy import text


class MySqlAiConfigurationRepository:
    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def get_enabled(self, ai_id: int) -> dict[str, Any]:
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, ai_name, ai_type, api_key, api_secret, api_url, "
                    "model_name, max_tokens, temperature, system_prompt "
                    "FROM ai_properties WHERE id=:ai_id AND is_enabled=1 "
                    "AND del_flag=0 LIMIT 1"
                ),
                {"ai_id": ai_id},
            )
            row = result.mappings().first()
        if row is None:
            raise LookupError(f"enabled AI configuration not found: {ai_id}")
        return {
            "id": int(row["id"]),
            "aiName": row.get("ai_name"),
            "aiType": row.get("ai_type"),
            "apiKey": row.get("api_key"),
            "apiSecret": row.get("api_secret"),
            "apiUrl": row.get("api_url"),
            "modelName": row.get("model_name"),
            "maxTokens": row.get("max_tokens"),
            "temperature": row.get("temperature"),
            "systemPrompt": row.get("system_prompt"),
        }
