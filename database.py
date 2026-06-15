import asyncpg
from config import DATABASE_URL

pool = None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

async def init_db():
    query = """
    -- существующие таблицы --
    CREATE TABLE IF NOT EXISTS order_history (
        id SERIAL PRIMARY KEY,
        order_id INT,
        courier_id BIGINT,
        rating INT,
        comment TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """
    await execute(query)

async def set_courier_status(tg_id, status: bool):
    await execute("UPDATE couriers SET online = $1 WHERE tg_id = $2", status, tg_id)

async def add_review(order_id, courier_id, rating, comment):
    await execute("INSERT INTO order_history (order_id, courier_id, rating, comment) VALUES ($1, $2, $3, $4)", 
                  order_id, courier_id, rating, comment)
    async with pool.acquire() as conn:
        await conn.execute(query)

async def execute(query, *args):
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

# --- Функции для работы ---
async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)

async def update_courier_verification(tg_id, status: bool):
    await execute("UPDATE couriers SET is_verified = $1 WHERE tg_id = $2", status, tg_id)

async def get_verified_couriers():
    return await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")

async def create_order(client_id, pickup, delivery, price):
    row = await fetch(
        "INSERT INTO orders (client_id, pickup_address, delivery_address, price, status) VALUES ($1, $2, $3, $4, 'pending') RETURNING id",
        client_id, pickup, delivery, price
    )
    return {'id': row[0][0], 'price': price}

async def update_order_status(order_id, status, courier_id=None):
    if courier_id:
        await execute("UPDATE orders SET status = $1, courier_id = $2 WHERE id = $3", status, courier_id, order_id)
    else:
        await execute("UPDATE orders SET status = $1 WHERE id = $2", status, order_id)

async def get_order_courier(order_id):
    row = await fetch("SELECT courier_id FROM orders WHERE id = $1", order_id)
    return row[0]['courier_id'] if row and row[0]['courier_id'] else None

async def cancel_order_db(order_id):
    await execute("UPDATE orders SET status = 'cancelled' WHERE id = $1", order_id)

# database.py

async def get_stats_data():
    """Возвращает общую статистику по выполненным заказам"""
    query = """
    SELECT 
        COUNT(*) as total_orders,
        AVG(rating) as avg_rating
    FROM order_history;
    """

# database.py

async def set_user_lang(tg_id, lang):
    """Сохраняет выбор языка пользователя"""
    await execute("UPDATE users SET lang = $1 WHERE tg_id = $2", lang, tg_id)

# database.py
async def get_waiting_orders():
    # Получаем все заказы, которые висят в ожидании
    return await fetch("SELECT * FROM orders WHERE status = 'waiting'")

async def set_order_waiting(order_id):
    await execute("UPDATE orders SET status = 'waiting' WHERE id = $1", order_id)

# Добавьте это в конец вашего файла database.py

async def get_waiting_orders():
    """Получает заказы, которые ждут курьера"""
    return await fetch("SELECT * FROM orders WHERE status = 'waiting'")

async def set_order_waiting(order_id):
    """Меняет статус заказа на ожидание"""
    await execute("UPDATE orders SET status = 'waiting' WHERE id = $1", order_id)

async def count_online_couriers():
    """Считает, сколько курьеров сейчас онлайн"""
    row = await fetch("SELECT COUNT(*) FROM couriers WHERE online = TRUE AND is_verified = TRUE")
    return row[0][0]

async def get_user_lang(tg_id):
    """Получает язык пользователя, по умолчанию 'ru'"""
    row = await fetch("SELECT lang FROM users WHERE tg_id = $1", tg_id)
    return row[0]['lang'] if row else 'ru'
    row = await fetch(query)
    return row[0] if row else None
