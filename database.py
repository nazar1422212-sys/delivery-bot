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

async def fetchval(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)

async def init_db():
    await execute("""
        CREATE TABLE IF NOT EXISTS users (tg_id BIGINT PRIMARY KEY, role TEXT, lang TEXT DEFAULT 'ru');
        CREATE TABLE IF NOT EXISTS couriers (tg_id BIGINT PRIMARY KEY, online BOOLEAN DEFAULT FALSE, is_verified BOOLEAN DEFAULT FALSE, card_number TEXT, passport_url TEXT, last_active TIMESTAMP DEFAULT NOW());
        CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, client_tg_id BIGINT, pickup_address TEXT, delivery_address TEXT, price DOUBLE PRECISION, payment_method TEXT, client_phone TEXT, vehicle_type TEXT DEFAULT 'standard', status TEXT DEFAULT 'waiting', courier_id BIGINT, created_at TIMESTAMP DEFAULT NOW());
        CREATE TABLE IF NOT EXISTS order_history (id SERIAL PRIMARY KEY, order_id INT, courier_id BIGINT, price DOUBLE PRECISION, rating INT, comment TEXT, created_at TIMESTAMP DEFAULT NOW());
    """)
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS vehicle_type TEXT DEFAULT 'standard';")

async def create_order(client_tg_id, pickup, delivery, price, method, phone, vehicle_type):
    query = """
        INSERT INTO orders (client_tg_id, pickup_address, delivery_address, price, payment_method, client_phone, vehicle_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
    """
    return await fetchval(query, client_tg_id, pickup, delivery, price, method, phone, vehicle_type)

async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)

async def create_courier(tg_id):
    await execute("INSERT INTO couriers (tg_id) VALUES ($1) ON CONFLICT (tg_id) DO NOTHING", tg_id)

async def get_verified_couriers():
    return await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")

async def get_waiting_orders():
    return await fetch("SELECT * FROM orders WHERE status = 'waiting'")

async def set_order_waiting(order_id):
    await execute("UPDATE orders SET status = 'waiting' WHERE id = $1", order_id)

async def update_order_status(order_id, status, courier_id=None):
    if courier_id:
        await execute("UPDATE orders SET status = $1, courier_id = $2 WHERE id = $3", status, courier_id, int(order_id))
    else:
        await execute("UPDATE orders SET status = $1 WHERE id = $2", status, int(order_id))

async def cancel_order_db(order_id):
    await execute("DELETE FROM orders WHERE id = $1 AND status IN ('waiting', 'pending');", int(order_id))

async def set_user_lang(tg_id, lang):
    await execute("UPDATE users SET lang = $1 WHERE tg_id = $2", lang, tg_id)

async def get_my_active_order(courier_tg_id):
    # Получает заказ, который курьер принял, но не завершил
    return await fetchval("SELECT * FROM orders WHERE courier_id = $1 AND status IN ('in_progress', 'at_pickup')", courier_tg_id)

async def update_order_status_db(order_id, status):
    await execute("UPDATE orders SET status = $1 WHERE id = $2", status, int(order_id))
