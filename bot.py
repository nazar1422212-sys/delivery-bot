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
import database as db
from config import TOKEN

bot = Bot(token=TOKEN)
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    vehicle_type = State()
    phone = State()

def get_maps_link(address):
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(address)}"

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Добро пожаловать! Используйте /order для заказа.")

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
    data = await state.get_data()
    phone = message.contact.phone_number if message.contact else message.text
    
    order_id = await db.create_order(
        message.from_user.id, data['pickup'], data['delivery'], 
        data['price'], "cash", phone, data['vehicle_type']
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{order_id}")]])
    await message.answer(f"✅ Заказ №{order_id} создан!\nЦена: {data['price']} лей.", reply_markup=kb)
    await state.clear()

async def check_queue():
    while True:
        orders = await db.get_waiting_orders()
        for order in orders:
            couriers = await db.get_verified_couriers()
            if couriers:
                text = (f"🔔 <b>Новый заказ №{order['id']}</b>\n"
                        f"📍 <a href='{get_maps_link(order['pickup_address'])}'>Откуда</a>\n"
                        f"🏁 <a href='{get_maps_link(order['delivery_address'])}'>Куда</a>\n"
                        f"💰 <b>Цена: {order['price']} лей</b>\n"
                        f"📞 Тел: {order['client_phone']}")
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")]])
                await bot.send_message(couriers[0]['tg_id'], text, reply_markup=kb, parse_mode=ParseMode.HTML)
                await db.update_order_status(order['id'], 'pending')
        await asyncio.sleep(10)

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = callback.data.split("_")[1]
    await db.update_order_status(order_id, 'in_progress', callback.from_user.id)
    await callback.message.edit_text(f"✅ Заказ №{order_id} принят!")

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_handler(callback: CallbackQuery):
    await db.cancel_order_db(callback.data.split("_")[1])
    await callback.message.edit_text("🚫 Заказ отменен.")

# Пример вызова
lang = await get_user_lang(message.from_user.id) # или 'ru' по умолчанию
await message.answer(get_text('order_created', lang, id=order_id, price=data['price']))

async def main():
    await db.connect_db()
    await db.init_db()
    keep_alive.run_web()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
