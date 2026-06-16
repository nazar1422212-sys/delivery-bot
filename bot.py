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
    set_order_waiting, create_courier, get_order_data, execute
)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    payment_method = State()

class FinishOrderForm(StatesGroup):
    waiting_for_finish_location = State()

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
    # ПРОВЕРЯЕМ, ПРИШЛА ЛИ ЛОКАЦИЯ
    if message.location:
        await state.update_data(delivery_lat=message.location.latitude, delivery_lon=message.location.longitude)
    else:
        # Если пришел текст
        await state.update_data(delivery=message.text)
    
    # ... переход к выбору оплаты ...
    
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
            method,
            data.get('pickup_lat'),
            data.get('pickup_lon'),
            data.get('delivery_lat'),
            data.get('delivery_lon')
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

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    try:
        order_id = callback.data.split("_")[1]
        # Обновляем статус заказа в БД на 'in_progress'
        await update_order_status(order_id, 'in_progress', callback.from_user.id)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📍 Я на месте (Точка А)", callback_data=f"at_pickup_{order_id}")],
            [InlineKeyboardButton(text="🏁 Завершить (Точка Б)", callback_data=f"finish_{order_id}")]
        ])
        await callback.message.edit_text(f"✅ Заказ №{order_id} принят! Двигайтесь к точке А.", reply_markup=kb)
    except Exception as e:
        print(f"ERROR: Failed to accept order: {e}")
        await callback.answer("❌ Ошибка при принятии заказа", show_alert=True)

@dp.message(F.photo)
async def handle_passport(message: Message):
    try:
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
    except Exception as e:
        print(f"ERROR: Failed to handle passport: {e}")
        await message.answer("❌ Ошибка при отправке паспорта")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    try:
        courier_id = callback.data.split("_")[1]
        await verify_courier(int(courier_id))
        await callback.message.edit_caption(caption=f"✅ Курьер {courier_id} одобрен!")
        await bot.send_message(int(courier_id), "🎉 Ваш аккаунт проверен! /online")
    except Exception as e:
        print(f"ERROR: Failed to approve courier: {e}")
        await callback.answer("❌ Ошибка при одобрении курьера", show_alert=True)

@dp.message(Command("online"))
async def go_online(message: Message):
    try:
        await set_courier_status(message.from_user.id, True)
        await message.answer("✅ Вы теперь онлайн и будете получать заказы!")
    except Exception as e:
        print(f"ERROR: Failed to set online status: {e}")
        await message.answer("❌ Ошибка при установке статуса")

@dp.message(Command("offline"))
async def go_offline(message: Message):
    try:
        await set_courier_status(message.from_user.id, False)
        await message.answer("💤 Вы ушли с линии. Заказы не будут приходить.")
    except Exception as e:
        print(f"ERROR: Failed to set offline status: {e}")
        await message.answer("❌ Ошибка при установке статуса")

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
    while True:
        try:
            # Получаем заказы, которые 'waiting' (без курьера)
            orders = await get_waiting_orders()
            for order in orders:
                couriers = await get_verified_couriers()  # Только онлайн и верифицированные
                if couriers:
                    # Отправляем заказ первому свободному курьеру
                    text = (f"🔔 **Новый заказ №{order['id']}**\n"
                            f"📍 {order['pickup_address']}\n"
                            f"🏁 {order['delivery_address']}\n"
                            f"💰 Цена: {order['price']} лей")
                    
                    # Добавляем кнопки принятия заказа
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Принять заказ", callback_data=f"accept_{order['id']}")]
                    ])
                    
                    await bot.send_message(couriers[0]['tg_id'], text, reply_markup=kb)
                    # Меняем статус на 'pending', чтобы бот не слал этот заказ снова
                    await update_order_status(order['id'], 'pending')
        except Exception as e:
            print(f"ERROR in check_queue: {e}")
        
        await asyncio.sleep(10)  # Проверка каждые 10 секунд

@dp.callback_query(F.data.startswith("finish_"))
async def finish_order_check(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = int(callback.data.split("_")[1])
        # Просим курьера прислать локацию для проверки
        await callback.message.answer("📍 Пожалуйста, пришлите вашу текущую геопозицию, чтобы завершить заказ.")
        await state.update_data(finishing_order=order_id)
        await state.set_state(FinishOrderForm.waiting_for_finish_location)
    except Exception as e:
        print(f"ERROR: Failed to start finish order: {e}")
        await callback.answer("❌ Ошибка при завершении заказа", show_alert=True)
        # В finalize_order в bot.py:
    try:
        price, dist = calculate_price(data['pickup'], data['delivery'])
    except Exception as e:
        print(f"Ошибка расчета: {e}")
        price, dist = 100.0, 0 # Безопасное значение при сбое

@dp.message(FinishOrderForm.waiting_for_finish_location, F.location)
async def verify_finish_location(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        order_id = data.get('finishing_order')
        
        if not order_id:
            await message.answer("❌ Ошибка: ID заказа не найден.")
            await state.clear()
            return
            
        order = await get_order_data(order_id)
        
        if not order:
            await message.answer("❌ Заказ не найден.")
            await state.clear()
            return
        
        if not order.get('delivery_lat') or not order.get('delivery_lon'):
            await message.answer("❌ Координаты доставки не найдены в заказе.")
            await state.clear()
            return
        
        # Расстояние между курьером и точкой Б
        courier_coords = (message.location.latitude, message.location.longitude)
        delivery_coords = (order['delivery_lat'], order['delivery_lon'])
        
        dist_meters = geodesic(courier_coords, delivery_coords).meters
        
        if dist_meters <= 100:
            await update_order_status(order_id, 'completed')
            await message.answer(f"🎉 Заказ №{order_id} успешно завершен! К оплате: {order['price']} лей.")
        else:
            await message.answer(f"❌ Вы слишком далеко ({int(dist_meters)} м). Нужно быть в радиусе 100 м.")
    except Exception as e:
        print(f"ERROR: Failed to verify finish location: {e}")
        await message.answer("❌ Ошибка при завершении заказа")
    finally:
        await state.clear()

@dp.message(Command("reset"))
async def reset_orders(message: Message):
    try:
        if message.from_user.id != int(ADMIN_ID):
            return await message.answer("❌ У вас нет прав для этой команды.")
        
        # Удаляем все заказы со статусом 'waiting' или 'pending'
        await execute("DELETE FROM orders WHERE status IN ('waiting', 'pending');")
        await message.answer("🧹 Все ожидающие заказы были удалены.")
    except Exception as e:
        print(f"ERROR: Failed to reset orders: {e}")
        await message.answer("❌ Ошибка при удалении заказов")

def calculate_price(addr1, addr2):
    # Увеличиваем таймаут до 10 секунд
    geolocator = Nominatim(user_agent="delivery_bot_v1", timeout=10) 
    try:
        loc1 = geolocator.geocode(addr1, language='ru')
        loc2 = geolocator.geocode(addr2, language='ru')
        
        if not loc1 or not loc2:
            return 50.0, 0 # Базовая цена, если адрес не найден
            
        dist = geodesic((loc1.latitude, loc1.longitude), (loc2.latitude, loc2.longitude)).km
        price = 50 + (dist * 10)
        return round(price, 0), round(dist, 1)
    except:
        return 50.0, 0 # Если сервер лежит, просто даем цену по умолчанию

async def main():
    try:
        await connect_db()
        await init_db()
        keep_alive.run_web()
        asyncio.create_task(check_queue())
        await dp.start_polling(bot)
    except Exception as e:
        print(f"CRITICAL ERROR in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
