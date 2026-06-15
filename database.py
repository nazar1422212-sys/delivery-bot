import asyncpg
from config import DATABASE_URL

pool = None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

async def execute(query, *args):
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def update_courier_verification(tg_id, status: bool):
    await execute("UPDATE couriers SET is_verified = $1 WHERE tg_id = $2", status, tg_id)

async def get_verified_couriers():
    return await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")
