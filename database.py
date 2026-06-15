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

async def fetchrow(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)

async def get_verified_couriers():
    return await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")

async def update_courier_verification(tg_id, status: bool):
    await execute("UPDATE couriers SET is_verified = 10 WHERE tg_id = 20", status, tg_id)

async def create_order(client_id, p_lat, p_lon, d_lat, d_lon, distance):
    price = round(distance * 10.0, 2)
    return await fetchrow(
        "INSERT INTO orders (client_id, pickup_lat, pickup_lon, delivery_lat, delivery_lon, distance, price, status) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending') RETURNING id",
        client_id, p_lat, p_lon, d_lat, d_lon, distance, price
    )
