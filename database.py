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


async def update_order_status(order_id, status, courier_id=None):
    """Обновляет статус заказа и привязывает курьера"""
    if courier_id:
        await execute("UPDATE orders SET status = $1, courier_id = $2 WHERE id = $3", status, courier_id, order_id)
    else:
        await execute("UPDATE orders SET status = $1 WHERE id = $2", status, order_id)

async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)

# 1. Импортируйте функцию set_user_role, если она у вас в database.py, 
# либо добавьте её туда. 
# Если её там нет, добавьте в database.py:
# async def set_user_role(tg_id, role):
#    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)

# 2. Добавьте этот блок в bot.py:

@dp.message(Command("start"))
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я Клиент", callback_data="role_client")],
        [InlineKeyboardButton(text="Я Курьер", callback_data="role_courier")]
    ])
    await message.answer("Добро пожаловать! Кто вы?", reply_markup=kb)

@dp.callback_query(F.data.startswith("role_"))
async def set_role(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    # Используем функцию из database.py для записи роли
    from database import set_user_role 
    await set_user_role(callback.from_user.id, role)
    
    if role == "client":
        await callback.message.edit_text("Вы зарегистрированы как Клиент. Используйте /order для создания заказа.")
    else:
        await callback.message.edit_text("Вы зарегистрированы как Курьер. Используйте /verify для верификации.")

async def set_user_role(tg_id, role):
    await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)
