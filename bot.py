import asyncio
import random
import urllib.parse
from geopy.geocoders import Nominatim
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

bot = Bot(token=TOKEN)
dp = Dispatcher()
geolocator = Nominatim(user_agent="delivery_bot")

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    vehicle_type = State()
    phone = State()

def get_coords(address):
    try:
        location = geolocator.geocode(address + ", Chisinau")
        return location.latitude, location.longitude
    except:
        return 0, 0

@dp.message(Command("start"))
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Клиент", callback_data="role_client"), 
         InlineKeyboardButton(text="Курьер", callback_data="role_courier")]
    ])
    await message.answer("Добро пожаловать! Выберите роль:", reply_markup=kb)

@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Введите адрес, откуда забрать:")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup)
async def process_pickup(message: Message, state: FSMContext):
    await state.update_data(pickup=message.text)
    await message.answer("📍 Введите адрес доставки:")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    await state.update_data(delivery=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Стандарт", callback_data="type_standard")],
        [InlineKeyboardButton(text="🚚 Грузовой", callback_data="type_cargo")]
    ])
    await message.answer("Выберите тип авто:", reply_markup=kb)
    await state.set_state(OrderForm.vehicle_type)

@dp.callback_query(OrderForm.vehicle_type, F.data.startswith("type_"))
async def process_vehicle(callback: CallbackQuery, state: FSMContext):
    v_type = callback.data.split("_")[1]
    price = random.randint(50, 100) if v_type == "standard" else random.randint(200, 600)
    await state.update_data(vehicle_type=v_type, price=price)
    
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить контакт", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await callback.message.answer("📞 Введите номер:", reply_markup=kb)
    await state.set_state(OrderForm.phone)

@dp.message(OrderForm.phone)
async def process_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    p_lat, p_lon = get_coords(data['pickup'])
    d_lat, d_lon = get_coords(data['delivery'])
    
    phone = message.contact.phone_number if message.contact else message.text
    
    order_id = await db.create_order(
        message.from_user.id, data['pickup'], data['delivery'], 
        data['price'], "cash", phone, data['vehicle_type'],
        p_lat, p_lon, d_lat, d_lon
    )
    
    lang = await db.get_user_lang(message.from_user.id)
    await message.answer(get_text('order_created', lang, id=order_id, price=data['price']))
    await state.clear()

async def check_queue():
    while True:
        orders = await db.get_waiting_orders()
        for order in orders:
            couriers = await db.get_verified_couriers()
            for courier in couriers:
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")]])
                await bot.send_message(courier['tg_id'], f"📦 Заказ №{order['id']}\nЦена: {order['price']} лей", reply_markup=kb)
                await db.update_order_status(order['id'], 'pending')
        await asyncio.sleep(10)

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = callback.data.split("_")[1]
    await db.update_order_status(order_id, 'in_progress', callback.from_user.id)
    await callback.message.edit_text(f"✅ Заказ №{order_id} принят!")

@dp.message(F.location)
async def handle_delivery_location(message: Message):
    order = await db.get_my_active_order(message.from_user.id)
    if not order: return

    dist = ((message.location.latitude - order['delivery_lat'])**2 + (message.location.longitude - order['delivery_lon'])**2)**0.5
    if dist < 0.005: 
        await db.update_order_status(order['id'], 'completed')
        await message.answer("🏁 Заказ завершен!")
    else:
        await message.answer("❌ Вы еще не у цели.")

async def main():
    await db.connect_db()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
