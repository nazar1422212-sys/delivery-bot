import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import TOKEN, ADMIN_ID
from database import connect_db, execute, update_courier_verification, get_verified_couriers
from keep_alive import run_web

# Инициализация
run_web()
bot = Bot(TOKEN)
dp = Dispatcher()

class CourierVerification(StatesGroup):
    waiting_for_doc = State()

# --- Обработчики ---

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Бот доставки запущен. Используйте /verify для регистрации курьера.")

@dp.message(Command("verify"))
async def start_verify(message: Message, state: FSMContext):
    await message.answer("Пришлите фото вашего документа.")
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
    await message.answer("Документы отправлены админу.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    c_id = int(callback.data.split("_")[1])
    await update_courier_verification(c_id, True)
    await callback.message.edit_caption(caption="✅ Курьер одобрен")
    await bot.send_message(c_id, "Ваш профиль подтвержден!")

# --- Запуск ---

async def main():
    await connect_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
