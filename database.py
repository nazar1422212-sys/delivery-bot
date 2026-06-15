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

# Функции ролей
async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)

# Функции верификации
async def update_courier_verification(tg_id, status: bool):
    await execute("UPDATE couriers SET is_verified = $1 WHERE tg_id = $2", status, tg_id)

async def get_verified_couriers():
    return await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")

# Функции заказов
async def create_order(client_id, p_lat, p_lon, d_lat, d_lon, distance):
    price = round(distance * 10.0, 2)
    row = await fetch("INSERT INTO orders (client_id, pickup_lat, pickup_lon, delivery_lat, delivery_lon, distance, price, status) VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending') RETURNING id",
                      client_id, p_lat, p_lon, d_lat, d_lon, distance, price)
    return {'id': row[0][0], 'price': price}

async def update_order_status(order_id, status, courier_id=None):
    if courier_id:
        await execute("UPDATE orders SET status = $1, courier_id = $2 WHERE id = $3", status, courier_id, order_id)
    else:
        await execute("UPDATE orders SET status = $1 WHERE id = $2", status, order_id)

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
    await execute(query)


