import asyncpg
import logging
from typing import Optional
from app.config import Settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def create_pool(settings: Settings) -> asyncpg.Pool:
    """Create asyncpg connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            min_size=2,
            max_size=10,
        )
        logger.info("Database connection pool created")
    return _pool


async def close_pool() -> None:
    """Close database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


def get_pool() -> Optional[asyncpg.Pool]:
    """Get database connection pool instance."""
    return _pool


async def init_db(pool: asyncpg.Pool) -> None:
    """Initialize database schema - create catalog_papers table if not exists."""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS catalog_papers (
                id UUID PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                author VARCHAR(300) NOT NULL,
                abstract_text TEXT,
                status VARCHAR(50),
                created_at TIMESTAMP,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("Database schema initialized")
