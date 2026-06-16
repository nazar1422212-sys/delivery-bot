import asyncio
import keep_alive
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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
    cancel_order_db, get_order_courier, get_user_lang, set_user_lang,
    set_passport_photo, verify_courier, delete_inactive_couriers, 
    update_courier_activity, set_courier_status, get_waiting_orders,
    set_order_waiting, create_courier
)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    payment_method = State()

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
    
    # Create courier record if role is courier
    if role == "courier":
        await create_courier(callback.from_user.id)
    
    await callback.message.answer(f"✅ Зарегистрированы как {role}")

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
    
    await message.answer("📍 Введите адрес доставки (или отправьте геопозицию):")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    if message.location:
        await state.update_data(delivery_lat=message.location.latitude, delivery_lon=message.location.longitude)
    else:
        await state.update_data(delivery=message.text)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Наличные", callback_data="pay_cash"), 
         InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")]
    ])
    await message.answer("✅ Выберите способ оплаты:", reply_markup=kb)
    await state.set_state(OrderForm.payment_method)

@dp.callback_query(OrderForm.payment_method, F.data.startswith("pay_"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    """Handle order finalization with price calculation"""
    await callback.answer()
    
    method = callback.data.split("_")[1]
    data = await state.get_data()
    
    # Validate required data
    if not data or ('pickup' not in data and 'pickup_lat' not in data):
        await callback.message.edit_text("❌ Ошибка: данные заказа не найдены. Начните заново /order")
        await state.clear()
        return
    
    # Calculate price based on available data
    price, dist = await calculate_price(data)
    
    # Create order in database
    try:
        order_id = await create_order(
            callback.from_user.id, 
            data.get('pickup', 'Coordinates provided'), 
            data.get('delivery', 'Coordinates provided'), 
            price, 
            method
        )
        
        if order_id:
            await set_order_waiting(order_id)
            await callback.message.edit_text(
                f"✅ Заказ №{order_id} создан!\nРасстояние: {dist} км\nИтого: {price} лей."
            )
        else:
            await callback.message.edit_text("❌ Ошибка при создании заказа. Попробуйте позже.")
    except Exception as e:
        print(f"ERROR: Failed to create order: {e}")
        await callback.message.edit_text("❌ Ошибка при создании заказа. Попробуйте позже.")
    
    await state.clear()

@dp.message(F.photo)
async def handle_passport(message: Message):
    photo_id = message.photo[-1].file_id
    await set_passport_photo(message.from_user.id, photo_id)
    await bot.send_photo(
        ADMIN_ID, 
        photo_id, 
        caption=f"🛂 Курьер {message.from_user.id} прислал паспорт. Одобрить?", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{message.from_user.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message.from_user.id}")
        ]])
    )
    await message.answer("✅ Паспорт получен. Ожидайте подтверждения.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    courier_id = callback.data.split("_")[1]
    await verify_courier(int(courier_id))
    await callback.message.edit_caption(caption=f"✅ Курьер {courier_id} одобрен!")
    await bot.send_message(int(courier_id), "🎉 Ваш аккаунт проверен! /online")

@dp.message(Command("online"))
async def go_online(message: Message):
    await set_courier_status(message.from_user.id, True)
    await update_courier_activity(message.from_user.id)
    await message.answer("✅ Вы онлайн!")

@dp.message(Command("offline"))
async def go_offline(message: Message):
    await set_courier_status(message.from_user.id, False)
    await update_courier_activity(message.from_user.id)
    await message.answer("💤 Вы ушли с линии.")

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer("🆘 *Помощь:*\n📦 /order - Заказ\n🚚 /online - Онлайн\n💤 /offline - Офлайн\n💳 /setcard - Карта")

async def calculate_price(data):
    """Calculate price based on either coordinates or address strings"""
    # If coordinates are available
    if 'pickup_lat' in data and 'delivery_lat' in data:
        try:
            dist = geodesic(
                (data['pickup_lat'], data['pickup_lon']), 
                (data['delivery_lat'], data['delivery_lon'])
            ).km
        except Exception as e:
            print(f"ERROR: Failed to calculate distance from coordinates: {e}")
            dist = 5.0
    else:
        # Calculate using address strings
        dist = await get_distance(data.get('pickup', ''), data.get('delivery', ''))
    
    price = 50 + (dist * 10)
    return round(price, 0), round(dist, 1)

async def get_distance(addr1, addr2):
    """Get distance between two addresses using geocoding"""
    if not addr1 or not addr2:
        return 5.0
    
    geolocator = Nominatim(user_agent="delivery_bot_v1")
    try:
        loc1 = geolocator.geocode(addr1, language='ru')
        loc2 = geolocator.geocode(addr2, language='ru')
        
        if not loc1 or not loc2:
            print(f"DEBUG: Could not find coordinates for: {addr1} or {addr2}")
            return 5.0
        
        dist = geodesic((loc1.latitude, loc1.longitude), (loc2.latitude, loc2.longitude)).km
        return round(dist, 1)
    except Exception as e:
        print(f"ERROR: Geocoding failed: {e}")
        return 5.0

async def check_queue():
    """Check waiting orders queue and assign to available couriers"""
    while True:
        try:
            waiting_orders = await get_waiting_orders()
            verified_couriers = await get_verified_couriers()
            
            if waiting_orders and verified_couriers:
                # Simple assignment: first available courier gets first order
                for order in waiting_orders:
                    for courier in verified_couriers:
                        await update_order_status(order['id'], 'assigned', courier['id'])
                        await bot.send_message(courier['id'], f"📦 Новый заказ №{order['id']}")
                        break
        except Exception as e:
            print(f"ERROR in check_queue: {e}")
        
        # Check queue every 10 seconds
        await asyncio.sleep(10)

def get_maps_link(lat1, lon1, lat2, lon2):
    return f"https://www.google.com/maps/dir/?api=1&origin={lat1},{lon1}&destination={lat2},{lon2}"

async def main():
    await connect_db()
    await init_db()
    keep_alive.run_web()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
