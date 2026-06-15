import asyncio

from aiogram import Bot
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

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
