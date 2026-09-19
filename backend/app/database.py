"""asyncpg pool; schema changes are tracked and applied transactionally."""

from pathlib import Path

import asyncpg


async def connect(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10, command_timeout=15)
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(817294613)")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            for migration in sorted((Path(__file__).parents[2] / "postgres").glob("*.sql")):
                if not await conn.fetchval("SELECT 1 FROM schema_migrations WHERE name=$1", migration.name):
                    await conn.execute(migration.read_text())
                    await conn.execute("INSERT INTO schema_migrations(name) VALUES($1)", migration.name)
        return pool
    except Exception:
        await pool.close()
        raise
