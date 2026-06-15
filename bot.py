import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import TOKEN, ADMIN_ID
from database import connect_db, execute, update_courier_verification
from keep_alive import run_web

# Запуск веб-сервера для Render
run_web()

bot = Bot(TOKEN)
dp = Dispatcher()

# Состояния
class CourierVerification(StatesGroup):
    waiting_for_doc = State()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Бот доставки запущен. Используйте /verify для регистрации курьера.")

# Верификация
@dp.message(Command("verify"))
async def start_verify(message: Message, state: FSMContext):
    await message.answer("Пришлите фото вашего паспорта.")
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
    await message.answer("Документы отправлены на проверку.")

# Обработка ответов админа
@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    c_id = int(callback.data.split("_")[1])
    await update_courier_verification(c_id, True)
    await callback.message.edit_caption(caption="✅ Курьер одобрен")
    await bot.send_message(c_id, "Ваш профиль подтвержден!")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_courier(callback: CallbackQuery):
    c_id = int(callback.data.split("_")[1])
    await callback.message.edit_caption(caption="❌ Курьер отклонен")
    await bot.send_message(c_id, "Ваши документы не прошли проверку.")

async def main():
    await connect_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

# bot.py

# Функция для отправки заказа курьеру
async def send_order_to_couriers(order_id, order_info):
    couriers = await get_verified_couriers()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order_id}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"decline_{order_id}")
        ]
    ])
    
    for courier in couriers:
        await bot.send_message(courier['tg_id'], f"Новый заказ #{order_id}!\n{order_info}", reply_markup=kb)

# Обработчик принятия заказа
@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    courier_id = callback.from_user.id
    
    # Проверяем, не занят ли уже заказ другим курьером (в БД)
    # Если свободен:
    await update_order_status(order_id, 'accepted', courier_id)
    await callback.message.edit_text("Вы приняли заказ! Отправляйтесь на точку А.")
    # Тут можно добавить логику отправки контактов клиента курьеру

# Обработчик отказа
@dp.callback_query(F.data.startswith("decline_"))
async def decline_order(callback: CallbackQuery):
    await callback.message.edit_text("Вы отказались от заказа.")
