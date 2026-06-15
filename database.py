import asyncpg
from config import DATABASE_URL

pool = None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

# Функция для создания таблиц, если их нет
async def init_db():
    query = """
    CREATE TABLE IF NOT EXISTS users(
        tg_id BIGINT PRIMARY KEY,
        username TEXT,
        role TEXT,
        phone TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS couriers(
        tg_id BIGINT PRIMARY KEY,
        lat DOUBLE PRECISION,
        lon DOUBLE PRECISION,
        online BOOLEAN DEFAULT TRUE,
        rating DOUBLE PRECISION DEFAULT 5,
        passport_url TEXT,
        is_verified BOOLEAN DEFAULT FALSE
    );
    CREATE TABLE IF NOT EXISTS orders(
        id SERIAL PRIMARY KEY,
        client_id BIGINT,
        courier_id BIGINT,
        pickup_lat DOUBLE PRECISION,
        pickup_lon DOUBLE PRECISION,
        delivery_lat DOUBLE PRECISION,
        delivery_lon DOUBLE PRECISION,
        distance DOUBLE PRECISION,
        price DOUBLE PRECISION,
        status TEXT,
        payment_status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    );
    """
    async with pool.acquire() as conn:
        await conn.execute(query)

async def execute(query, *args):
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

# Ваши остальные функции...
async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)
    await execute(query)


