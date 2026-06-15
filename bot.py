import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import TOKEN, ADMIN_ID
from database import connect_db, execute, update_courier_verification
from keep_alive import run_web

# Запуск веб-сервера для Render
run_web()

bot = Bot(TOKEN)
dp = Dispatcher()

# Состояния
class CourierVerification(StatesGroup):
    waiting_for_doc = State()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Бот доставки запущен. Используйте /verify для регистрации курьера.")

# Верификация
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
    await message.answer("Документы отправлены на проверку.")

# Обработка ответов админа
@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    c_id = int(callback.data.split("_")[1])
    await update_courier_verification(c_id, True)
    await callback.message.edit_caption(caption="✅ Курьер одобрен")
    await bot.send_message(c_id, "Ваш профиль подтвержден!")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_courier(callback: CallbackQuery):
    c_id = int(callback.data.split("_")[1])
    await callback.message.edit_caption(caption="❌ Курьер отклонен")
    await bot.send_message(c_id, "Ваши документы не прошли проверку.")

async def main():
    await connect_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

# bot.py

# Функция для отправки заказа курьеру
async def send_order_to_couriers(order_id, order_info):
    couriers = await get_verified_couriers()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order_id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"decline_{order_id}")
        ]
    ])
    
    for courier in couriers:
        await bot.send_message(courier['tg_id'], f"Новый заказ #{order_id}!\n{order_info}", reply_markup=kb)

# Обработчик принятия заказа
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    courier_id = callback.from_user.id
    
    # Проверяем, не занят ли уже заказ другим курьером (в БД)
    # Если свободен:
    await update_order_status(order_id, 'accepted', courier_id)
    await callback.message.edit_text("Вы приняли заказ! Отправляйтесь на точку А.")
    # Тут можно добавить логику отправки контактов клиента курьеру

# Обработчик отказа
@dp.callback_query(F.data.startswith("decline_"))
async def decline_order(callback: CallbackQuery):
    await callback.message.edit_text("Вы отказались от заказа.")

# Состояние заказа
class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()

@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Отправьте геолокацию точки А (посадка).")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup, F.location)
async def process_pickup(message: Message, state: FSMContext):
    await state.update_data(pickup=(message.location.latitude, message.location.longitude))
    await message.answer("Отправьте геолокацию точки Б (доставка).")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery, F.location)
async def process_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    p_lat, p_lon = data['pickup']
    d_lat, d_lon = message.location.latitude, message.location.longitude
    
    # Расчет (упрощенно, как прямая линия)
    distance = ((d_lat - p_lat)**2 + (d_lon - p_lon)**2)**0.5 * 111 
    price = round(distance * 10.0, 2)
    
    # Сохранение в БД
    order = await create_order(message.from_user.id, p_lat, p_lon, d_lat, d_lon, distance)
    
    await message.answer(f"Заказ создан! Стоимость: {price} лей.\nОплата: Наличными курьеру.")
    await state.clear()
    
    # Рассылка курьерам (функция из предыдущих шагов)
    await send_order_to_couriers(order['id'], f"Точка А: {p_lat}, {p_lon}\nТочка Б: {d_lat}, {d_lon}\nЦена: {price} лей")

from geopy.distance import geodesic

async def is_near_location(courier_lat, courier_lon, target_lat, target_lon):
    # Расстояние в метрах
    distance = geodesic((courier_lat, courier_lon), (target_lat, target_lon)).meters
    return distance <= 100

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    # ... логика обновления статуса в БД ...
    
    # Клавиатура для курьера
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Я на месте (Точка А)", callback_data=f"arrived_{order_id}")],
        [InlineKeyboardButton(text="💰 Оплата получена", callback_data=f"paid_{order_id}")]
    ])
    await callback.message.edit_text("Заказ принят! Жмите 'Я на месте' при прибытии.", reply_markup=kb)

# Обработка прибытия
@dp.callback_query(F.data.startswith("arrived_"))
async def courier_arrived(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    # Здесь нужно получить координаты курьера (из БД или последнего сообщения)
    # Если дистанция < 100м:
    await bot.send_message(client_id, "Курьер прибыл на точку!")
    await callback.answer("Уведомление отправлено клиенту!")
