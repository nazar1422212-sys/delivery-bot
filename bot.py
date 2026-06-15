import asyncio

from aiogram import Bot
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from keep_alive import run_web
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()

@dp.message(Command("order"))
async def start_order(message: Message, state: FSMContext):
    await message.answer("Отправьте геолокацию точки А (посадка).")
    await state.set_state(OrderForm.pickup)

@dp.message(OrderForm.pickup)
async def process_pickup(message: Message, state: FSMContext):
    # Здесь должна быть логика сохранения координат
    await state.update_data(pickup=message.location)
    await message.answer("Теперь отправьте геолокацию точки Б (доставка).")
    await state.set_state(OrderForm.delivery)

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    # Логика расчета расстояния и вызова create_order
    await message.answer("Заказ создан! Стоимость рассчитана в леях.")
    await state.clear()

run_web()

from config import TOKEN
from database import connect_db

bot = Bot(TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Бот доставки запущен"
    )

async def main():

    await connect_db()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
