import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import TOKEN, ADMIN_ID
from database import connect_db, update_courier_verification, get_verified_couriers, update_order_status, create_order, set_user_role
from keep_alive import run_web

run_web()

bot = Bot(TOKEN)
dp = Dispatcher()

# --- Состояния ---
class CourierVerification(StatesGroup):
    waiting_for_doc = State()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()

# --- Регистрация роли ---
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

# --- Верификация и Заказы (остальной ваш код обработчиков) ---
@dp.message(Command("verify"))
async def start_verify(message: Message, state: FSMContext):
    await message.answer("Пришлите фото паспорта.")
    await state.set_state(CourierVerification.waiting_for_doc)

# ... (Здесь должны быть ваши остальные обработчики: handle_photo, accept_order, process_delivery и т.д.) ...

async def main():
    await connect_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
