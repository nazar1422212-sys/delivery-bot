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

class Verification(StatesGroup):
    waiting_for_photo = State()

@dp.message(Command("verify"))
async def start_verification(message: Message, state: FSMContext):
    await message.answer("Пришлите фото вашего документа (паспорта) для верификации.")
    await state.set_state(Verification.waiting_for_photo)

@dp.message(Verification.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    # Сохраняем photo_id в БД для курьера
    await execute("UPDATE couriers SET passport_url = $1 WHERE tg_id = $2", photo_id, message.from_user.id)
    await message.answer("Документ принят на проверку администратором.")
    await state.clear()
    def calculate_order(distance):
    total_price = distance * 10  # 10 лей за км
    my_fee = total_price * 0.05
    courier_gets = total_price - my_fee
    return total_price, my_fee, courier_gets
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_courier_keyboard(lat, lon):
    # Ссылка на Google Maps для навигации
    map_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    builder = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Открыть маршрут", url=map_url)],
        [InlineKeyboardButton(text="Я на месте", callback_data="arrived")]
    ])
    return builder
