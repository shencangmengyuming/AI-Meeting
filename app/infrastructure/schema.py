from typing import Any

from sqlalchemy import text

MYSQL_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS t_user (
        id BIGINT NOT NULL AUTO_INCREMENT,
        username VARCHAR(128) NOT NULL,
        password VARCHAR(255) NOT NULL,
        real_name VARCHAR(128) NULL,
        phone VARCHAR(32) NULL,
        mail VARCHAR(255) NULL,
        del_flag TINYINT NOT NULL DEFAULT 0,
        create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        UNIQUE KEY uq_t_user_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_permission (
        id BIGINT NOT NULL AUTO_INCREMENT,
        username VARCHAR(128) NOT NULL,
        is_admin TINYINT NOT NULL DEFAULT 0,
        del_flag TINYINT NOT NULL DEFAULT 0,
        create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        UNIQUE KEY uq_admin_permission_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_properties (
        id BIGINT NOT NULL AUTO_INCREMENT,
        ai_name VARCHAR(128) NOT NULL,
        ai_type VARCHAR(64) NULL,
        api_key VARCHAR(512) NULL,
        api_secret VARCHAR(512) NULL,
        api_url VARCHAR(1024) NULL,
        model_name VARCHAR(255) NULL,
        max_tokens INT NULL,
        temperature DECIMAL(5,3) NULL,
        system_prompt TEXT NULL,
        is_enabled TINYINT NOT NULL DEFAULT 1,
        del_flag TINYINT NOT NULL DEFAULT 0,
        create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        KEY idx_ai_properties_enabled (is_enabled, del_flag)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_properties (
        id BIGINT NOT NULL AUTO_INCREMENT,
        agent_name VARCHAR(128) NOT NULL,
        api_key VARCHAR(512) NULL,
        api_secret VARCHAR(512) NULL,
        api_flow_id VARCHAR(255) NULL,
        del_flag TINYINT NOT NULL DEFAULT 0,
        create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        PRIMARY KEY (id),
        KEY idx_agent_properties_name (agent_name, del_flag)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_file_asset (
        id BIGINT NOT NULL AUTO_INCREMENT,
        agent_id BIGINT NOT NULL,
        session_id VARCHAR(128) NULL,
        user_name VARCHAR(128) NOT NULL,
        biz_type VARCHAR(128) NULL,
        source_platform VARCHAR(64) NULL,
        file_name VARCHAR(512) NOT NULL,
        file_ext VARCHAR(64) NULL,
        content_type VARCHAR(255) NULL,
        file_size BIGINT NOT NULL DEFAULT 0,
        file_url VARCHAR(2048) NOT NULL,
        upload_status VARCHAR(64) NOT NULL,
        create_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        update_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ON UPDATE CURRENT_TIMESTAMP(6),
        del_flag TINYINT NOT NULL DEFAULT 0,
        PRIMARY KEY (id),
        KEY idx_agent_file_session (session_id, user_name, del_flag)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)


async def ensure_mysql_schema(engine: Any) -> None:
    async with engine.begin() as connection:
        for statement in MYSQL_SCHEMA:
            await connection.execute(text(statement))
