from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text

from app.auth_user.application.registration import USERNAME_BLOOM_KEY


@dataclass(frozen=True)
class BloomRebuildStats:
    scanned: int


async def rebuild_user_bloom(
    session_factory,
    redis,
    *,
    batch_size: int = 1000,
    capacity: int = 100_000_000,
    error_rate: float = 0.001,
) -> BloomRebuildStats:
    temporary_key = f"{USERNAME_BLOOM_KEY}:rebuild:{uuid4()}"
    await redis.delete(temporary_key)
    await redis.execute_command(
        "BF.RESERVE", temporary_key, error_rate, capacity
    )
    scanned = 0
    offset = 0
    try:
        while True:
            async with session_factory() as session:
                result = await session.execute(
                    text(
                        "SELECT username FROM t_user WHERE del_flag=0 "
                        "ORDER BY id LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": batch_size, "offset": offset},
                )
                rows = result.all()
            if not rows:
                break
            for row in rows:
                username = row[0] if not hasattr(row, "username") else row.username
                await redis.execute_command("BF.ADD", temporary_key, str(username))
                scanned += 1
            offset += len(rows)
        await redis.rename(temporary_key, USERNAME_BLOOM_KEY)
    except Exception:
        await redis.delete(temporary_key)
        raise
    return BloomRebuildStats(scanned=scanned)
