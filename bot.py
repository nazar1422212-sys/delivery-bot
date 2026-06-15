import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from geopy.distance import geodesic

from config import TOKEN, ADMIN_ID
from database import connect_db, execute, update_courier_verification, get_verified_couriers, update_order_status, create_order, set_user_role
from keep_alive import run_web

# Запуск веб-сервера для Render
run_web()

bot = Bot(TOKEN)
dp = Dispatcher()

# --- Состояния ---
class CourierVerification(StatesGroup):
    waiting_for_doc = State()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()

# --- 1. Регистрация роли (для разделения Клиент/Курьер) ---
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
    await set_user_role(callback.from_user.id, role)
    await callback.message.edit_text(f"Вы зарегистрированы как {role.capitalize()}.")

# --- 2. Верификация курьера ---
@dp.message(Command("verify"))
async def start_verify(message: Message, state: FSMContext):
    await message.answer("Пришлите фото вашего паспорта.")
    await state.set_state(CourierVerification.waiting_for_doc)

@dp.message(CourierVerification.waiting_for_doc, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{message.from_user.id}")],
        [InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, photo_id, caption=f"Курьер {message.from_user.id} на проверке.", reply_markup=kb)
    await state.clear()
    await message.answer("Документы отправлены.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    c_id = int(callback.data.split("_")[1])
    await update_courier_verification(c_id, True)
    await callback.message.edit_caption(caption="✅ Курьер одобрен")
    await bot.send_message(c_id, "Ваш профиль подтвержден!")

# --- 3. Логика заказа ---
async def send_order_to_couriers(order_id, order_info):
    couriers = await get_verified_couriers()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order_id}")],
        [InlineKeyboardButton(text="❌ Отказать", callback_data=f"decline_{order_id}")]
    ])
    for courier in couriers:
        await bot.send_message(courier['tg_id'], f"Новый заказ #{order_id}!\n{order_info}", reply_markup=kb)

@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Отправьте геолокацию точки А.")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup, F.location)
async def process_pickup(message: Message, state: FSMContext):
    await state.update_data(pickup=(message.location.latitude, message.location.longitude))
    await message.answer("Отправьте геолокацию точки Б.")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery, F.location)
async def process_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    p_lat, p_lon = data['pickup']
    order = await create_order(message.from_user.id, p_lat, p_lon, message.location.latitude, message.location.longitude, 5.0)
    await message.answer("Заказ создан!")
    await state.clear()
    await send_order_to_couriers(order['id'], f"Цена: {order['price']} лей")

# --- 4. Логика курьера (Принятие, на месте, оплата) ---
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    await update_order_status(order_id, 'accepted', callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Я на месте", callback_data=f"arrived_{order_id}")],
        [InlineKeyboardButton(text="💰 Получил оплату", callback_data=f"paid_{order_id}")]
    ])
    await callback.message.edit_text("Вы приняли заказ! Жмите 'Я на месте' при прибытии.", reply_markup=kb)

@dp.callback_query(F.data.startswith("paid_"))
async def finish_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    await update_order_status(order_id, 'finished')
    await callback.message.edit_text("Заказ успешно закрыт. Спасибо!")

async def main():
    await connect_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
