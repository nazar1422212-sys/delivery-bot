import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import keep_alive # Исправлено
from config import TOKEN, ADMIN_ID
from translations import get_text
from database import (
    connect_db, init_db, set_user_role, get_verified_couriers, 
    update_order_status, create_order, cancel_order_db, 
    get_order_courier, get_user_lang, set_user_lang, 
    set_order_waiting, get_waiting_orders, get_courier_history
)

bot = Bot(TOKEN)
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    payment_method = State()

# --- Единый Start ---
@dp.message(Command("start"))
async def start(message: Message):
    lang = await get_user_lang(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
         InlineKeyboardButton(text="🇷🇴 Română", callback_data="lang_ro")]
    ])
    await message.answer("Выберите язык / Alegeți limba:", reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def set_lang(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    await set_user_lang(callback.from_user.id, lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('client', lang), callback_data="role_client")],
        [InlineKeyboardButton(text=get_text('courier', lang), callback_data="role_courier")]
    ])
    await callback.message.edit_text(get_text('welcome', lang), reply_markup=kb)

# --- Фоновая задача ---
async def check_queue():
    while True:
        orders = await get_waiting_orders()
        for order in orders:
            couriers = await get_verified_couriers()
            if couriers:
                await bot.send_message(couriers[0]['tg_id'], f"🔔 Новый заказ №{order['id']}")
                await update_order_status(order['id'], 'pending')
        await asyncio.sleep(30)

async def main():
    await connect_db()
    await init_db()
    asyncio.create_task(check_queue()) # Запуск очереди
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
