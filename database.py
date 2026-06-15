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
    await execute("""
        CREATE TABLE IF NOT EXISTS users (tg_id BIGINT PRIMARY KEY, role TEXT, lang TEXT DEFAULT 'ru');
        CREATE TABLE IF NOT EXISTS couriers (tg_id BIGINT PRIMARY KEY, online BOOLEAN DEFAULT FALSE, is_verified BOOLEAN DEFAULT FALSE, card_number TEXT);
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY, client_id BIGINT, courier_id BIGINT, 
            pickup_address TEXT, delivery_address TEXT, price DOUBLE PRECISION, 
            status TEXT DEFAULT 'waiting', payment_method TEXT, payment_status TEXT DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS order_history (
            id SERIAL PRIMARY KEY, order_id INT, courier_id BIGINT, 
            price DOUBLE PRECISION, rating INT, comment TEXT, created_at TIMESTAMP DEFAULT NOW()
        );
    """)

# Функции ролей и статусов
async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)

async def set_courier_status(tg_id, status: bool):
    await execute("UPDATE couriers SET online = $1 WHERE tg_id = $2", status, tg_id)

async def get_verified_couriers():
    return await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")

# Функции заказов и очереди
async def create_order(client_id, pickup, delivery, price, payment_method):
    row = await fetch("INSERT INTO orders (client_id, pickup_address, delivery_address, price, payment_method) VALUES ($1, $2, $3, $4, $5) RETURNING id", 
                      client_id, pickup, delivery, price, payment_method)
    return row[0][0]

async def set_order_waiting(order_id):
    await execute("UPDATE orders SET status = 'waiting' WHERE id = $1", order_id)

async def get_waiting_orders():
    return await fetch("SELECT * FROM orders WHERE status = 'waiting'")

async def update_order_status(order_id, status, courier_id=None):
    if courier_id:
        await execute("UPDATE orders SET status = $1, courier_id = $2 WHERE id = $3", status, courier_id, order_id)
    else:
        await execute("UPDATE orders SET status = $1 WHERE id = $2", status, order_id)

# Статистика и история
async def add_review(order_id, courier_id, price, rating, comment):
    await execute("INSERT INTO order_history (order_id, courier_id, price, rating, comment) VALUES ($1, $2, $3, $4, $5)", order_id, courier_id, price, rating, comment)

async def get_courier_history(courier_id):
    return await fetch("SELECT order_id, price, rating FROM order_history WHERE courier_id = $1 ORDER BY created_at DESC LIMIT 10", courier_id)

async def get_stats_data():
    row = await fetch("SELECT COUNT(*) as total_orders, AVG(rating) as avg_rating FROM order_history")
    return row[0]

async def get_user_lang(tg_id):
    row = await fetch("SELECT lang FROM users WHERE tg_id = $1", tg_id)
    return row[0]['lang'] if row else 'ru'

async def set_user_lang(tg_id, lang):
    await execute("UPDATE users SET lang = $1 WHERE tg_id = $2", lang, tg_id)

# database.py

# Добавьте в конец файла database.py

async def set_passport_photo(tg_id, photo_id):
    """Сохранить ID фото паспорта курьера"""
    await execute("UPDATE couriers SET passport_url = $1 WHERE tg_id = $2", photo_id, tg_id)

async def verify_courier(tg_id):
    """Одобрить курьера админом"""
    await execute("UPDATE couriers SET is_verified = TRUE WHERE tg_id = $1", tg_id)

# Функции для истории уже были (add_review и get_courier_history), 
# убедитесь, что они тоже есть в database.py
# database.py

async def delete_inactive_couriers():
    """Удаляет курьеров, которые не заходили (не меняли статус) более 60 дней"""
    # Допустим, у вас есть поле last_active или мы проверяем время регистрации
    # Самый надежный способ - добавить колонку last_active в таблицу couriers
    query = """
    DELETE FROM couriers 
    WHERE last_active < NOW() - INTERVAL '60 days';
    """
# database.py

async def init_db():
    # Добавьте эту строку в init_db, если колонка еще не создана
    await execute("ALTER TABLE couriers ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT NOW();")
    
    # ... остальной код ...

async def delete_inactive_couriers():
    """Удаляет курьеров, которые не были активны более 60 дней"""
    query = """
    DELETE FROM couriers 
    WHERE last_active < NOW() - INTERVAL '60 days';
    """
    await execute(query)

async def update_courier_activity(tg_id):
    """Обновляет время активности курьера (вызывать при каждом /online или /offline)"""
    await execute("UPDATE couriers SET last_active = NOW() WHERE tg_id = $1", tg_id)
    await execute(query)
