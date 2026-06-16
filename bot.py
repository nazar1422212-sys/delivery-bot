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
from translations import get_text
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
    lang = await db.get_user_lang(message.from_user.id)
    await message.answer(get_text('welcome', lang))

@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    lang = await db.get_user_lang(message.from_user.id)
    await message.answer(get_text('enter_phone', lang))
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
    
    lang = await db.get_user_lang(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_text('cancel', lang), callback_data=f"cancel_{order_id}")]])
    await message.answer(get_text('order_created', lang, id=order_id, price=data['price']), reply_markup=kb)
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
    lang = await db.get_user_lang(callback.from_user.id)
    await callback.message.edit_text(get_text('order_accepted', lang, id=order_id), reply_markup=get_courier_kb(order_id))

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_handler(callback: CallbackQuery):
    await db.cancel_order_db(callback.data.split("_")[1])
    lang = await db.get_user_lang(callback.from_user.id)
    await callback.message.edit_text(get_text('order_cancelled', lang))

def get_courier_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Я на месте (А)", callback_data=f"at_pickup_{order_id}")],
        [InlineKeyboardButton(text="🏁 Я на месте (Б)", callback_data=f"at_delivery_{order_id}")]
    ])

# --- ЛОГИКА ТАЙМЕРА КЛИЕНТА ---
async def client_timeout_timer(order_id):
    await asyncio.sleep(3600) # 1 час
    order = await db.get_order_data(order_id)
    if order and order['status'] != 'completed':
        await bot.send_message(order['courier_id'], "⚠️ Клиент не подтвердил прибытие. Можете оставить заказ себе.")

# --- ОБРАБОТЧИКИ КУРЬЕРА ---
@dp.callback_query(F.data.startswith("at_pickup_"))
async def at_pickup(callback: CallbackQuery):
    order_id = callback.data.split("_")[2]
    await db.update_order_status(order_id, 'at_pickup')
    order = await db.get_order_data(order_id)
    
    # Уведомление клиенту
    lang = await db.get_user_lang(order['client_tg_id'])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_text('client_ok', lang), callback_data=f"client_ok_{order_id}")]])
    await bot.send_message(order['client_tg_id'], get_text('at_pickup_notify', lang), reply_markup=kb)
    asyncio.create_task(client_timeout_timer(order_id))
    await callback.answer("Клиент уведомлен")

@dp.callback_query(F.data.startswith("at_delivery_"))
async def at_delivery(callback: CallbackQuery):
    order_id = callback.data.split("_")[2]
    await db.update_order_status(order_id, 'completed')
    order = await db.get_order_data(order_id)
    
    lang = await db.get_user_lang(order['client_tg_id'])
    await bot.send_message(order['client_tg_id'], get_text('delivery_done', lang))
    await callback.message.edit_text("🏁 Заказ завершен!")

@dp.message(F.location)
async def handle_delivery_location(message: Message):
    order = await db.get_active_order_for_courier(message.from_user.id)
    if not order: return

    # Расчет дистанции (при��лизительно)
    dist = ((message.location.latitude - order['delivery_lat'])**2 + 
            (message.location.longitude - order['delivery_lon'])**2)**0.5
    
    if dist < 0.001: # 100 метров
        await db.update_order_status(order['id'], 'completed')
        lang = await db.get_user_lang(message.from_user.id)
        await message.answer(get_text('delivery_done', lang))
        await bot.send_message(order['client_tg_id'], get_text('delivery_done', lang))
    else:
        await message.answer("❌ Вы далеко от точки доставки. Подойдите ближе.")

# --- СПИСОК ДОСТУПНЫХ ЗАКАЗОВ ---
@dp.message(Command("active_orders"))
async def show_orders(message: Message):
    orders = await db.get_all_waiting_orders()
    for order in orders:
        text = f"📦 Заказ №{order['id']}\nЦена: {order['price']} лей"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")]])
        await message.answer(text, reply_markup=kb)

# --- КЛИЕНТСКИЕ ОБРАБОТЧИКИ ---
@dp.callback_query(F.data.startswith("client_ok_"))
async def client_ok(callback: CallbackQuery):
    lang = await db.get_user_lang(callback.from_user.id)
    await callback.answer("Спасибо! Курьер продолжает работу.")
    await callback.message.edit_text(get_text('client_ok', lang))


async def main():
    await db.connect_db()
    await db.init_db()
    keep_alive.run_web()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
