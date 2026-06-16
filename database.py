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
    """Fetch a single scalar value - used for RETURNING queries"""
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)

async def init_db():
    # Создаем таблицы, если их нет
    await execute("""
        CREATE TABLE IF NOT EXISTS users (tg_id BIGINT PRIMARY KEY, role TEXT, lang TEXT DEFAULT 'ru');
        CREATE TABLE IF NOT EXISTS couriers (tg_id BIGINT PRIMARY KEY, online BOOLEAN DEFAULT FALSE, is_verified BOOLEAN DEFAULT FALSE, card_number TEXT, passport_url TEXT, last_active TIMESTAMP DEFAULT NOW());
        CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, client_id BIGINT, pickup_address TEXT, delivery_address TEXT, pickup_lat DOUBLE PRECISION, pickup_lon DOUBLE PRECISION, delivery_lat DOUBLE PRECISION, delivery_lon DOUBLE PRECISION, price DOUBLE PRECISION, status TEXT DEFAULT 'waiting', payment_method TEXT, payment_status TEXT DEFAULT 'pending', courier_id BIGINT, client_phone TEXT, client_tg_id BIGINT, created_at TIMESTAMP DEFAULT NOW());
        CREATE TABLE IF NOT EXISTS order_history (id SERIAL PRIMARY KEY, order_id INT, courier_id BIGINT, price DOUBLE PRECISION, rating INT, comment TEXT, created_at TIMESTAMP DEFAULT NOW());
    """)
    
    # Принудительно добавляем недостающие колонки в таблицу orders
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_address TEXT;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_address TEXT;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_lat DOUBLE PRECISION;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_lon DOUBLE PRECISION;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_lat DOUBLE PRECISION;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_lon DOUBLE PRECISION;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS price DOUBLE PRECISION;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'waiting';")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method TEXT;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'pending';")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS courier_id BIGINT;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS client_phone TEXT;")
    await execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS client_tg_id BIGINT;")

async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)

async def create_courier(tg_id):
    """Create a new courier record"""
    await execute("INSERT INTO couriers (tg_id) VALUES ($1) ON CONFLICT (tg_id) DO NOTHING", tg_id)

async def set_courier_status(tg_id, status: bool):
    await execute("UPDATE couriers SET online = $1 WHERE tg_id = $2", status, tg_id)

async def get_verified_couriers():
    return await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")

async def create_order(client_tg_id, pickup, delivery, price, method, p_lat, p_lon, d_lat, d_lon, phone):
    query = """
        INSERT INTO orders (client_tg_id, pickup_address, delivery_address, price, payment_method, 
                            pickup_lat, pickup_lon, delivery_lat, delivery_lon, client_phone)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id
    """
    row = await fetchval(query, client_tg_id, pickup, delivery, price, method, p_lat, p_lon, d_lat, d_lon, phone)
    return row

async def set_order_waiting(order_id):
    await execute("UPDATE orders SET status = 'waiting' WHERE id = $1", order_id)

async def get_waiting_orders():
    return await fetch("SELECT * FROM orders WHERE status = 'waiting'")

async def update_order_status(order_id, status, courier_id=None):
    order_id = int(order_id)  # Ensure order_id is integer
    if courier_id:
        courier_id = int(courier_id)  # Ensure courier_id is integer
        await execute("UPDATE orders SET status = $1, courier_id = $2 WHERE id = $3", status, courier_id, order_id)
    else:
        await execute("UPDATE orders SET status = $1 WHERE id = $2", status, order_id)

async def add_review(order_id, courier_id, price, rating, comment):
    await execute("INSERT INTO order_history (order_id, courier_id, price, rating, comment) VALUES ($1, $2, $3, $4, $5)", order_id, courier_id, price, rating, comment)

async def get_courier_history(courier_id):
    return await fetch("SELECT order_id, price, rating FROM order_history WHERE courier_id = $1 ORDER BY created_at DESC LIMIT 10", courier_id)

async def get_user_lang(tg_id):
    row = await fetch("SELECT lang FROM users WHERE tg_id = $1", tg_id)
    return row[0]['lang'] if row else 'ru'

async def set_user_lang(tg_id, lang):
    await execute("UPDATE users SET lang = $1 WHERE tg_id = $2", lang, tg_id)

async def set_passport_photo(tg_id, photo_id):
    await execute("UPDATE couriers SET passport_url = $1 WHERE tg_id = $2", photo_id, tg_id)

async def verify_courier(tg_id):
    await execute("UPDATE couriers SET is_verified = TRUE WHERE tg_id = $1", tg_id)

async def delete_inactive_couriers():
    await execute("DELETE FROM couriers WHERE last_active < NOW() - INTERVAL '60 days';")

async def update_courier_verification(tg_id, is_verified: bool):
    await execute("UPDATE couriers SET is_verified = $1 WHERE tg_id = $2", is_verified, tg_id)

async def update_courier_activity(tg_id):
    await execute("UPDATE couriers SET last_active = NOW() WHERE tg_id = $1", tg_id)

async def cancel_order_db(order_id):
    query = "DELETE FROM orders WHERE id = $1 AND status IN ('waiting', 'pending');"
    await execute(query, int(order_id))

async def get_order_courier(order_id):
    row = await fetch("SELECT courier_id FROM orders WHERE id = $1", order_id)
    return row[0]['courier_id'] if row else None

async def get_order_data(order_id):
    """Get order data by order_id"""
    row = await fetch("SELECT * FROM orders WHERE id = $1", order_id)
    return row[0] if row else None
