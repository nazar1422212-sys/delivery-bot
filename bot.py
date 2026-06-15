import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from geopy.distance import geodesic
from database import connect_db, init_db
from config import TOKEN, ADMIN_ID
from database import connect_db, update_courier_verification, get_verified_couriers, update_order_status, create_order, set_user_role
from keep_alive import run_web

run_web()
bot = Bot(TOKEN)
dp = Dispatcher()

class CourierVerification(StatesGroup):
    waiting_for_doc = State()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()

# --- Логика Ролей ---
@dp.message(Command("start"))
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я Клиент", callback_data="role_client")],
        [InlineKeyboardButton(text="Я Курьер", callback_data="role_courier")]
    ])
    await message.answer("Добро пожаловать! Кто вы?", reply_markup=kb)

@dp.callback_query(F.data.startswith("role_"))
async def set_role(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    await set_user_role(callback.from_user.id, role)
    await callback.message.edit_text(f"Вы зарегистрированы как {role.capitalize()}.")

# --- Верификация ---
@dp.message(Command("verify"))
async def start_verify(message: Message, state: FSMContext):
    await message.answer("Пришлите фото паспорта.")
    await state.set_state(CourierVerification.waiting_for_doc)

@dp.message(CourierVerification.waiting_for_doc, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{message.from_user.id}")],
        [InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, photo_id, caption=f"Курьер {message.from_user.id} на проверке.", reply_markup=kb)
    await state.clear()
    await message.answer("Документы отправлены.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    c_id = int(callback.data.split("_")[1])
    await update_courier_verification(c_id, True)
    await callback.message.edit_caption(caption="✅ Курьер одобрен")

# --- Логика Заказов ---
@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Отправьте геопозицию точки А.")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup, F.location)
async def process_pickup(message: Message, state: FSMContext):
    await state.update_data(pickup=(message.location.latitude, message.location.longitude))
    await message.answer("Отправьте геопозицию точки Б.")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery, F.location)
async def process_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    p_lat, p_lon = data['pickup']
    # Сохраняем и уведомляем
    order = await create_order(message.from_user.id, p_lat, p_lon, message.location.latitude, message.location.longitude, 5.0)
    await message.answer(f"Заказ создан! Стоимость: {order['price']} лей.")
    await state.clear()
    # Рассылка курьерам
    couriers = await get_verified_couriers()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")]
    ])
    for c in couriers:
        await bot.send_message(c['tg_id'], "Новый заказ!", reply_markup=kb)

# --- Принятие и завершение ---
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    await update_order_status(order_id, 'accepted', callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 На месте", callback_data=f"arrived_{order_id}")],
        [InlineKeyboardButton(text="💰 Оплачено", callback_data=f"paid_{order_id}")]
    ])
    await callback.message.edit_text("Заказ принят!", reply_markup=kb)

@dp.callback_query(F.data.startswith("paid_"))
async def finish_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    await update_order_status(order_id, 'finished')
    await callback.message.edit_text("Заказ закрыт!")

# ... (здесь импорты и все обработчики @dp.message ...)

async def main():
    await connect_db()
    await init_db()  # <-- ВОТ ЗДЕСЬ ОНО ДОЛЖНО БЫТЬ!
    print("База данных инициализирована.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
