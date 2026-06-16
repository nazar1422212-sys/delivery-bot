import asyncio
import keep_alive
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from translations import get_text
from config import TOKEN, ADMIN_ID
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from database import (
    connect_db, init_db, set_user_role, update_courier_verification, 
    get_verified_couriers, update_order_status, create_order, 
    get_user_lang, set_user_lang, set_passport_photo, verify_courier, 
    set_courier_status, get_waiting_orders, set_order_waiting, 
    create_courier, get_order_data, execute
)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    phone = State()
    payment_method = State()

class FinishOrderForm(StatesGroup):
    waiting_for_finish_location = State()

# --- СТАРТ И РЕГИСТРАЦИЯ ---
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
    if role == "courier":
        await create_courier(callback.from_user.id)
    await callback.message.answer(f"✅ Зарегистрированы как {role}")

# --- ОФОРМЛЕНИЕ ЗАКАЗА ---
@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Введите адрес, откуда забрать:")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup)
async def process_pickup(message: Message, state: FSMContext):
    if message.location:
        await state.update_data(pickup_lat=message.location.latitude, pickup_lon=message.location.longitude)
    else:
        await state.update_data(pickup=message.text)
    await state.set_state(OrderForm.delivery)
    await message.answer("📍 Введите адрес доставки (или отправьте геопозицию):")

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    if message.location:
        await state.update_data(delivery_lat=message.location.latitude, delivery_lon=message.location.longitude)
    else:
        await state.update_data(delivery=message.text)
    
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("📞 Введите ваш номер телефона или нажмите кнопку:", reply_markup=kb)
    await state.set_state(OrderForm.phone)

# 1. ОБРАБОТКА ТЕЛЕФОНА
@dp.message(OrderForm.phone)
async def process_phone(message: Message, state: FSMContext):
    # Получаем телефон
    phone = message.contact.phone_number if message.contact else message.text
    
    # Сохраняем в память
    await state.update_data(phone=phone)
    
    # Создаем клавиатуру выбора оплаты
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Наличные", callback_data="pay_cash"), 
         InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")]
    ])
    
    # ПЕРЕХОД В СОСТОЯНИЕ ОПЛАТЫ
    await state.set_state(OrderForm.payment_method)
    
    await message.answer("✅ Номер сохранен! Выберите способ оплаты:", reply_markup=kb)

# 2. ОБРАБОТКА ОПЛАТЫ (ОБЯЗАТЕЛЬНО С DECORATOR)
@dp.callback_query(OrderForm.payment_method, F.data.startswith("pay_"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1] # "cash" или "card"
    data = await state.get_data()
    
    # Расчет цены
    price, dist = await calculate_price(data)
    
    # Сохраняем данные в БД
    order_id = await create_order(
        client_tg_id=callback.from_user.id,
        pickup=data.get('pickup', 'Geo'),
        delivery=data.get('delivery', 'Geo'),
        price=price,
        method=method,
        p_lat=data.get('pickup_lat'),
        p_lon=data.get('pickup_lon'),
        d_lat=data.get('delivery_lat'),
        d_lon=data.get('delivery_lon'),
        client_phone=data.get('phone')
    )

    if order_id:
        await set_order_waiting(order_id)
        await callback.message.edit_text(f"✅ Заказ №{order_id} создан!\nРасстояние: {dist} км\nИтого: {price} лей.")
    else:
        await callback.message.edit_text("❌ Ошибка базы данных при создании заказа.")
    
    await state.clear()

# --- КУРЬЕРСКИЕ ФУНКЦИИ ---
async def check_queue():
    while True:
        orders = await get_waiting_orders()
        for order in orders:
            couriers = await get_verified_couriers()
            if couriers:
                # Добавляем цену и расстояние в текст
                # Используем .get() для безопасности, если каких-то полей вдруг нет
                text = (f"🔔 **Новый заказ №{order['id']}**\n"
                        f"📍 От: {order['pickup_address']}\n"
                        f"🏁 До: {order['delivery_address']}\n"
                        f"💰 Цена: {order.get('price', '0')} лей\n"
                        f"📏 Расстояние: {order.get('distance', '0')} км\n"
                        f"📞 Тел: {order['client_phone']}\n"
                        f"👤 <a href='tg://user?id={order['client_tg_id']}'>Написать клиенту</a>")
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Принять заказ", callback_data=f"accept_{order['id']}")]
                ])
                
                await bot.send_message(
                    couriers[0]['tg_id'], 
                    text, 
                    reply_markup=kb, 
                    parse_mode=ParseMode.HTML
                )
                await update_order_status(order['id'], 'pending')
        await asyncio.sleep(10)

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = callback.data.split("_")[1]
    await update_order_status(order_id, 'in_progress', callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏁 Завершить", callback_data=f"finish_{order_id}")]])
    await callback.message.edit_text(f"✅ Заказ №{order_id} принят!", reply_markup=kb)

# --- УТИЛИТЫ ---
async def calculate_price(data):
    lat1, lon1, lat2, lon2 = data.get('pickup_lat'), data.get('pickup_lon'), data.get('delivery_lat'), data.get('delivery_lon')
    if all([lat1, lon1, lat2, lon2]):
        dist = geodesic((lat1, lon1), (lat2, lon2)).km
    else:
        dist = await get_distance(data.get('pickup', ''), data.get('delivery', ''))
    return round(50 + (dist * 10), 0), round(dist, 1)

async def get_distance(addr1, addr2):
    geolocator = Nominatim(user_agent="delivery_bot_v1")
    try:
        loc1 = geolocator.geocode(addr1)
        loc2 = geolocator.geocode(addr2)
        return round(geodesic((loc1.latitude, loc1.longitude), (loc2.latitude, loc2.longitude)).km, 1) if loc1 and loc2 else 5.0
    except: return 5.0

async def main():
    await connect_db()
    await init_db()
    keep_alive.run_web()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
