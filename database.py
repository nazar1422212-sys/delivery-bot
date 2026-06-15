import asyncpg
from config import DATABASE_URL

pool = None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)

# Упрощенный доступ к пулу
async def fetch(query, *args):
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def execute(query, *args):
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def create_order(client_id, p_lat, p_lon, d_lat, d_lon, distance):
    price = round(distance * 10.0, 2)  # Расчет цены в леях 
    return await fetch(
        "INSERT INTO orders (client_id, pickup_lat, pickup_lon, delivery_lat, delivery_lon, distance, price, status) VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending') RETURNING id",
        client_id, p_lat, p_lon, d_lat, d_lon, distance, price
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram import F

ADMIN_ID = 123456789 # Вставьте сюда ваш ID

@dp.message(CourierVerification.waiting_for_doc, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    
    # Отправляем админу фото и кнопки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{message.from_user.id}")],
        [InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_{message.from_user.id}")]
    ])
    
    await bot.send_photo(ADMIN_ID, photo_id, caption=f"Курьер {message.from_user.id} прислал доки.", reply_markup=kb)
    await message.answer("Ваши документы отправлены на проверку.")
    await state.clear()
