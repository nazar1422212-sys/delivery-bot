import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from translations import get_text
import keep_alive
from database import *
from config import TOKEN, ADMIN_ID

bot = Bot(TOKEN)
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    payment_method = State()

# --- Старт и Роли ---
@dp.message(Command("start"))
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton(text="🇷🇴 Română", callback_data="lang_ro")]
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

@dp.callback_query(F.data.startswith("role_"))
async def set_role(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    await set_user_role(callback.from_user.id, role)
    await callback.message.answer(f"✅ Зарегистрированы как {role}")

# --- Оформление заказа ---
@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Введите адрес, откуда забрать:")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup)
async def process_pickup(message: Message, state: FSMContext):
    await state.update_data(pickup=message.text)
    await message.answer("Введите адрес доставки:")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    await state.update_data(delivery=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Наличные", callback_data="pay_cash"), InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")]
    ])
    await message.answer("Выберите способ оплаты:", reply_markup=kb)
    await state.set_state(OrderForm.payment_method)

@dp.callback_query(OrderForm.payment_method, F.data.startswith("pay_"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1]
    data = await state.get_data()
    order_id = await create_order(callback.from_user.id, data['pickup'], data['delivery'], 50.0, method)
    await set_order_waiting(order_id)
    await callback.message.edit_text(f"✅ Заказ №{order_id} создан и поставлен в очередь!")
    await state.clear()

# --- Фоновая задача очереди ---
async def check_queue():
    while True:
        orders = await get_waiting_orders()
        for order in orders:
            couriers = await get_verified_couriers()
            if couriers:
                await bot.send_message(couriers[0]['tg_id'], f"🔔 Новый заказ №{order['id']}!")
                await update_order_status(order['id'], 'pending')
        await asyncio.sleep(30)

async def main():
    await connect_db()
    await init_db()
    keep_alive.run_web()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)


@dp.message(F.photo)
async def handle_passport(message: Message):
    # Проверяем, является ли пользователь курьером (можно добавить проверку в БД)
    photo_id = message.photo[-1].file_id
    await set_passport_photo(message.from_user.id, photo_id)
    
    # Отправляем вам (Админу)
    await bot.send_photo(ADMIN_ID, photo_id, 
                         caption=f"🛂 Курьер {message.from_user.id} прислал паспорт. Одобрить?", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{message.from_user.id}")]
                         ]))
    await message.answer("✅ Паспорт получен. Ожидайте подтверждения от администратора.")

if __name__ == "__main__":
    asyncio.run(main())
