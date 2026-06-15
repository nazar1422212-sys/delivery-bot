import asyncpg
from config import DATABASE_URL

pool = None

async def connect_db():
    global pool

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10
    )

async def execute(query, *args):
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def fetchrow(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)
