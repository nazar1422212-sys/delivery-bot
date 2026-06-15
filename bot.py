import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорт всех функций из database
from database import (
    connect_db, init_db, set_user_role, update_courier_verification, 
    get_verified_couriers, update_order_status, create_order, 
    cancel_order_db, get_order_courier
)
from config import TOKEN, ADMIN_ID
from translations import get_text

bot = Bot(TOKEN)
dp = Dispatcher()

# Состояния для оформления заказа
class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()

# --- Логика Ролей ---
@dp.message(Command("start"))
async def start(message: Message):
    lang = 'ro' # Можно сделать выбор языка в БД
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('client', lang), callback_data="role_client")],
        [InlineKeyboardButton(text=get_text('courier', lang), callback_data="role_courier")]
    ])
    await message.answer(get_text('welcome', lang), reply_markup=kb)

@dp.callback_query(F.data.startswith("role_"))
async def set_role(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    await set_user_role(callback.from_user.id, role)
    await callback.message.edit_text(f"Вы зарегистрированы как {role.capitalize()}.")

# --- Заказы (текстовые адреса) ---
@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Введите адрес, откуда забрать:")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup)
async def process_pickup(message: Message, state: FSMContext):
    await state.update_data(pickup=message.text)
    await message.answer("Введите адрес доставки:")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    order = await create_order(message.from_user.id, data['pickup'], message.text, 50.0)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{order['id']}")]
    ])
    await message.answer(f"✅ Заказ №{order['id']} создан! Стоимость: 50 лей.", reply_markup=kb)
    await state.clear()
    
    # Рассылка курьерам
    couriers = await get_verified_couriers()
    for c in couriers:
        kb_acc = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}") ]])
        await bot.send_message(c['tg_id'], f"📦 Новый заказ №{order['id']}\nОткуда: {data['pickup']}\nКуда: {message.text}", reply_markup=kb_acc)

# --- Обработка действий ---
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    courier_id = await get_order_courier(order_id)
    await cancel_order_db(order_id)
    await callback.message.edit_text("❌ Заказ отменен.")
    if courier_id:
        try: await bot.send_message(courier_id, f"⚠️ Заказ №{order_id} отменен клиентом.")
        except: pass

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    await update_order_status(order_id, 'accepted', callback.from_user.id)
    await callback.message.edit_text("✅ Заказ принят!")

async def main():
    await connect_db()
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
