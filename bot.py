import asyncio
import random
import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
import database as db
from translations import get_text
from config import TOKEN
import keep_alive

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()
geolocator = Nominatim(user_agent="delivery_bot", timeout=5)

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    vehicle_type = State()
    phone = State()

async def get_coords(address):
    """Async geocoding to avoid blocking"""
    try:
        loop = asyncio.get_event_loop()
        location = await loop.run_in_executor(None, geolocator.geocode, address + ", Chisinau")
        if location:
            return location.latitude, location.longitude
        logger.warning(f"No location found for: {address}")
        return None, None
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        logger.error(f"Geolocation error: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error in get_coords: {e}")
        return None, None

@dp.message(Command("start"))
async def start(message: Message):
    """Handle /start command - register user and show role selection"""
    try:
        await db.set_user_role(message.from_user.id, 'pending')
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Клиент", callback_data="role_client"), 
             InlineKeyboardButton(text="Курьер", callback_data="role_courier")]
        ])
        await message.answer("Добро пожаловать! Выберите роль:", reply_markup=kb)
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await message.answer("❌ Ошибка. Попробуйте позже.")

@dp.callback_query(F.data == "role_client")
async def select_client_role(callback: CallbackQuery):
    """Handle client role selection"""
    try:
        await db.set_user_role(callback.from_user.id, 'client')
        await callback.message.edit_text("✅ Вы выбрали роль Клиент!\n\nИспользуйте /order для создания заказа")
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in client role selection: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.callback_query(F.data == "role_courier")
async def select_courier_role(callback: CallbackQuery):
    """Handle courier role selection"""
    try:
        await db.set_user_role(callback.from_user.id, 'courier')
        await db.create_courier(callback.from_user.id)
        await callback.message.edit_text("✅ Вы выбрали роль Курьер!\n\nВы будете получать предложения заказов")
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in courier role selection: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    """Start order creation flow"""
    try:
        await message.answer("Введите адрес, откуда забрать:")
        await state.set_state(OrderForm.pickup)
    except Exception as e:
        logger.error(f"Error in start_order: {e}")
        await message.answer("❌ Ошибка. Попробуйте позже.")

@dp.message(OrderForm.pickup)
async def process_pickup(message: Message, state: FSMContext):
    """Process pickup address"""
    try:
        await state.update_data(pickup=message.text)
        await message.answer("📍 Введите адрес доставки:")
        await state.set_state(OrderForm.delivery)
    except Exception as e:
        logger.error(f"Error in process_pickup: {e}")
        await message.answer("❌ Ошибка. Попробуйте снова.")

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    """Process delivery address"""
    try:
        await state.update_data(delivery=message.text)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Стандарт", callback_data="type_standard")],
            [InlineKeyboardButton(text="🚚 Грузовой", callback_data="type_cargo")]
        ])
        await message.answer("Выберите тип авто:", reply_markup=kb)
        await state.set_state(OrderForm.vehicle_type)
    except Exception as e:
        logger.error(f"Error in process_delivery: {e}")
        await message.answer("❌ Ошибка. Попробуйте снова.")

@dp.callback_query(OrderForm.vehicle_type, F.data.startswith("type_"))
async def process_vehicle(callback: CallbackQuery, state: FSMContext):
    """Process vehicle type selection"""
    try:
        v_type = callback.data.split("_")[1]
        price = random.randint(50, 100) if v_type == "standard" else random.randint(200, 600)
        await state.update_data(vehicle_type=v_type, price=price)
        
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить контакт", request_contact=True)]], 
                               resize_keyboard=True, one_time_keyboard=True)
        await callback.message.answer("📞 Введите номер:", reply_markup=kb)
        await state.set_state(OrderForm.phone)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in process_vehicle: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.message(OrderForm.phone)
async def process_phone(message: Message, state: FSMContext):
    """Process phone number and create order"""
    try:
        data = await state.get_data()
        
        # Validate required data
        if not data or 'pickup' not in data or 'delivery' not in data or 'price' not in data:
            await message.answer("❌ Ошибка: неполные данные. Начните заново: /order")
            await state.clear()
            return
        
        # Get phone number
        phone = message.contact.phone_number if message.contact else message.text
        if not phone:
            await message.answer("❌ Пожалуйста, укажите номер телефона")
            return
        
        # Get coordinates
        p_lat, p_lon = await get_coords(data['pickup'])
        d_lat, d_lon = await get_coords(data['delivery'])
        
        # Create order
        order_id = await db.create_order(
            message.from_user.id, data['pickup'], data['delivery'], 
            data['price'], "cash", phone, data['vehicle_type'],
            p_lat, p_lon, d_lat, d_lon
        )
        
        if not order_id:
            await message.answer("❌ Ошибка создания заказа. Попробуйте позже.")
            await state.clear()
            return
        
        lang = await db.get_user_lang(message.from_user.id)
        await message.answer(get_text('order_created', lang, id=order_id, price=data['price']))
        await state.clear()
    except Exception as e:
        logger.error(f"Error in process_phone: {e}")
        await message.answer("❌ Ошибка при обработке заказа.")
        await state.clear()

async def check_queue():
    """Background task to check for waiting orders and notify couriers"""
    logger.info("Order queue checker started")
    while True:
        try:
            orders = await db.get_waiting_orders()
            if not orders:
                await asyncio.sleep(10)
                continue
            
            for order in orders:
                try:
                    couriers = await db.get_verified_couriers()
                    if not couriers:
                        logger.warning(f"No verified couriers for order {order['id']}")
                        continue
                    
                    for courier in couriers:
                        try:
                            kb = InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")]
                            ])
                            await bot.send_message(
                                courier['tg_id'], 
                                f"📦 Заказ №{order['id']}\nЦена: {order['price']} лей", 
                                reply_markup=kb
                            )
                        except Exception as e:
                            logger.error(f"Error sending message to courier {courier['tg_id']}: {e}")
                    
                    await db.update_order_status(order['id'], 'pending')
                except Exception as e:
                    logger.error(f"Error processing order {order['id']}: {e}")
            
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error in check_queue: {e}")
            await asyncio.sleep(10)

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    """Handle order acceptance by courier"""
    try:
        order_id = int(callback.data.split("_")[1])
        await db.update_order_status(order_id, 'in_progress', callback.from_user.id)
        await callback.message.edit_text(f"✅ Заказ №{order_id} принят!")
        await callback.answer()
    except ValueError:
        logger.error(f"Invalid order_id in callback: {callback.data}")
        await callback.answer("❌ Ошибка", show_alert=True)
    except Exception as e:
        logger.error(f"Error in accept_order: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@dp.message(F.location)
async def handle_delivery_location(message: Message):
    """Handle location sharing for delivery completion"""
    try:
        order = await db.get_my_active_order(message.from_user.id)
        if not order: 
            await message.answer("У вас нет активных заказов")
            return

        # Check if delivery coordinates exist
        if order['delivery_lat'] is None or order['delivery_lon'] is None:
            await message.answer("⚠️ Координаты доставки недоступны")
            return

        # Calculate distance
        dist = ((message.location.latitude - order['delivery_lat'])**2 + 
               (message.location.longitude - order['delivery_lon'])**2)**0.5
        
        if dist < 0.005:  # ~500 meters
            await db.update_order_status(order['id'], 'completed')
            await message.answer("🏁 Заказ завершен!")
        else:
            await message.answer(f"❌ Вы еще не у цели. Расстояние: {dist:.4f}°")
    except Exception as e:
        logger.error(f"Error in handle_delivery_location: {e}")
        await message.answer("❌ Ошибка при обработке локации")

async def main():
    """Initialize bot and start polling"""
    try:
        logger.info("Initializing database...")
        await db.connect_db()
        await db.init_db()
        logger.info("Database initialized successfully")
        
        # Start background tasks
        asyncio.create_task(check_queue())
        keep_alive.run_web()  # Start Flask keep-alive server
        
        logger.info("Bot started successfully!")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
