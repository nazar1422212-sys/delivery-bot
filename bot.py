import asyncio
import random
import urllib.parse
import keep_alive
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import TOKEN
from database import (
    connect_db, init_db, set_user_role, get_verified_couriers, update_order_status, 
    create_order, create_courier, get_waiting_orders, set_order_waiting, cancel_order_db
)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    vehicle_type = State()
    phone = State()

def get_google_maps_link(address):
    if not address: return "#"
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(address)}"

# --- ОСНОВНАЯ ЛОГИКА ---

@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Введите адрес, откуда забрать:")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup)
async def process_pickup(message: Message, state: FSMContext):
    await state.update_data(pickup=message.text)
    await state.set_state(OrderForm.delivery)
    await message.answer("📍 Введите адрес доставки:")

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    await state.update_data(delivery=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Стандарт (30-100 лей)", callback_data="type_standard")],
        [InlineKeyboardButton(text="🚚 Грузовой (200-600 лей)", callback_data="type_cargo")]
    ])
    await message.answer("Выберите тип авто:", reply_markup=kb)
    await state.set_state(OrderForm.vehicle_type)

@dp.callback_query(OrderForm.vehicle_type, F.data.startswith("type_"))
async def process_vehicle(callback: CallbackQuery, state: FSMContext):
    v_type = callback.data.split("_")[1]
    price = random.randint(30, 100) if v_type == "standard" else random.randint(200, 600)
    await state.update_data(vehicle_type=v_type, price=price)
    
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await callback.message.answer("📞 Введите ваш номер телефона или нажмите кнопку:", reply_markup=kb)
    await state.set_state(OrderForm.phone)

@dp.message(OrderForm.phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    data = await state.update_data(phone=phone)
    
    order_id = await create_order(
        client_tg_id=message.from_user.id,
        pickup=data['pickup'],
        delivery=data['delivery'],
        price=data['price'],
        method="cash",
        client_phone=phone
    )

    if order_id:
        await set_order_waiting(order_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{order_id}")]])
        await message.answer(f"✅ Заказ №{order_id} создан!\nЦена: {data['price']} лей.", reply_markup=kb)
    await state.clear()

async def check_queue():
    while True:
        orders = await get_waiting_orders()
        for order in orders:
            couriers = await get_verified_couriers()
            if couriers:
                p_link = get_google_maps_link(order['pickup_address'])
                d_link = get_google_maps_link(order['delivery_address'])
                
                text = (f"🔔 <b>Новый заказ №{order['id']}</b>\n"
                        f"📍 <a href='{p_link}'>От: {order['pickup_address']}</a>\n"
                        f"🏁 <a href='{d_link}'>До: {order['delivery_address']}</a>\n"
                        f"💰 <b>Цена: {order.get('price', 0)} лей</b>\n"
                        f"📞 Тел: {order['client_phone']}")
                
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")]])
                await bot.send_message(couriers[0]['tg_id'], text, reply_markup=kb)
                await update_order_status(order['id'], 'pending')
        await asyncio.sleep(10)

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_handler(callback: CallbackQuery):
    order_id = callback.data.split("_")[1]
    await cancel_order_db(order_id)
    await callback.message.edit_text("🚫 Заказ отменен.")

async def main():
    await connect_db()
    await init_db()
    keep_alive.run_web()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
