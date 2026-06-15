import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from translations import get_text
import keep_alive
from database import *
from config import TOKEN, ADMIN_ID
# bot.py

# bot.py

# bot.py

from database import (
    connect_db, init_db, set_user_role, update_courier_verification, 
    get_verified_couriers, update_order_status, create_order, 
    cancel_order_db, get_order_courier, get_user_lang
)

bot = Bot(TOKEN)
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    payment_method = State()

# --- Старт и Роли ---
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
    await callback.message.answer(f"✅ Зарегистрированы как {role}")

# --- Оформление заказа ---
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
    await state.update_data(delivery=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Наличные", callback_data="pay_cash"), InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")]
    ])
    await message.answer("Выберите способ оплаты:", reply_markup=kb)
    await state.set_state(OrderForm.payment_method)

@dp.callback_query(OrderForm.payment_method, F.data.startswith("pay_"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1]
    data = await state.get_data()
    order_id = await create_order(callback.from_user.id, data['pickup'], data['delivery'], 50.0, method)
    await set_order_waiting(order_id)
    await callback.message.edit_text(f"✅ Заказ №{order_id} создан и поставлен в очередь!")
    await state.clear()
# bot.py

# bot.py

async def check_queue():
    while True:
        # 1. Проверяем очередь заказов (часто)
        orders = await get_waiting_orders()
        for order in orders:
            couriers = await get_verified_couriers()
            if couriers:
                await bot.send_message(couriers[0]['tg_id'], f"🔔 Новый заказ №{order['id']}!")
                await update_order_status(order['id'], 'pending')
        
        # 2. Очистка неактивных (редко, раз в 24 часа)
        # Чтобы не писать сложный таймер, можно проверять время внутри цикла
        await delete_inactive_couriers()
        
        # Пауза 86400 секунд = 24 часа
        await asyncio.sleep(86400)

async def main():
    await connect_db()
    await init_db()
    keep_alive.run_web() # Запуск веб-сервера для Render
    asyncio.create_task(check_queue()) # Обязательно для очереди заказов
    await dp.start_polling(bot)


@dp.message(F.photo)
async def handle_passport(message: Message):
    # Проверяем, является ли пользователь курьером (можно добавить проверку в БД)
    photo_id = message.photo[-1].file_id
    await set_passport_photo(message.from_user.id, photo_id)
    
    # Отправляем вам (Админу)
    await bot.send_photo(ADMIN_ID, photo_id, 
                         caption=f"🛂 Курьер {message.from_user.id} прислал паспорт. Одобрить?", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{message.from_user.id}")]
                         ]))
    await message.answer("✅ Паспорт получен. Ожидайте подтверждения от администратора.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    courier_id = callback.data.split("_")[1]
    await verify_courier(int(courier_id))
    
    await callback.message.edit_caption(caption=f"✅ Курьер {courier_id} одобрен!")
    await bot.send_message(int(courier_id), "🎉 Ваш аккаунт проверен! Теперь вы можете работать: /online")

# bot.py

# ... (ваш код выше) ...

# Добавьте сюда обработчики команд для курьеров
@dp.message(Command("online"))
async def go_online(message: Message):
    # Убедитесь, что функции set_courier_status и update_courier_activity импортированы из database
    await set_courier_status(message.from_user.id, True)
    await update_courier_activity(message.from_user.id) # Сброс счетчика удаления
    await message.answer("✅ Вы онлайн! Теперь вы будете получать заказы.")

@dp.message(Command("offline"))
async def go_offline(message: Message):
    await set_courier_status(message.from_user.id, False)
    # Здесь можно тоже обновить активность, если хотите
    await update_courier_activity(message.from_user.id) 
    await message.answer("💤 Вы ушли с линии.")

# ... (ваш остальной код, например функция main()) ...

@dp.message(Command("help"))
async def help_command(message: Message):
    text = """
🆘 **Помощь по боту:**

📦 **Заказ доставки:** `/order`
📜 **История:** `/history`

🚚 **Для курьеров:**
✅ Стать онлайн: `/online`
💤 Уйти с линии: `/offline`
💳 Привязать карту: `/setcard`

*Чтобы начать принимать заказы, отправьте боту фото паспорта для проверки.*
    """
    await message.answer(text, parse_mode="Markdown")

if __name__ == "__main__":
    asyncio.run(main())
