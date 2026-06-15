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

async def init_db():
    # Создаем таблицы (включая order_history с правильными полями)
    await execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id SERIAL PRIMARY KEY,
            order_id INT,
            courier_id BIGINT,
            price DOUBLE PRECISION,
            rating INT,
            comment TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

async def add_review(order_id, courier_id, price, rating, comment):
    query = "INSERT INTO order_history (order_id, courier_id, price, rating, comment) VALUES ($1, $2, $3, $4, $5)"
    await execute(query, order_id, courier_id, price, rating, comment)

async def get_waiting_orders():
    return await fetch("SELECT * FROM orders WHERE status = 'waiting'")

async def set_order_waiting(order_id):
    await execute("UPDATE orders SET status = 'waiting' WHERE id = $1", order_id)

async def count_online_couriers():
    row = await fetch("SELECT COUNT(*) FROM couriers WHERE online = TRUE AND is_verified = TRUE")
    return row[0][0]

async def get_user_lang(tg_id):
    row = await fetch("SELECT lang FROM users WHERE tg_id = $1", tg_id)
    return row[0]['lang'] if row else 'ru'

async def get_courier_history(courier_id):
    return await fetch("SELECT order_id, price, rating FROM order_history WHERE courier_id = $1 ORDER BY created_at DESC LIMIT 10", courier_id)
