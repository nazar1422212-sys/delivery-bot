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

# --- Переключение статуса курьера ---
@dp.message(Command("online"))
async def go_online(message: Message):
    await set_courier_status(message.from_user.id, True)
    await message.answer("✅ Вы онлайн и готовы принимать заказы!")

@dp.message(Command("offline"))
async def go_offline(message: Message):
    await set_courier_status(message.from_user.id, False)
    await message.answer("💤 Вы офлайн. Заказы больше не будут приходить.")

# --- Система отзывов (после выполнения заказа) ---
# После того как курьер нажал "Доставлено" и клиент получил заказ:
async def ask_for_review(client_id, order_id, courier_id):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{order_id}_{courier_id}_1"),
         InlineKeyboardButton(text="⭐⭐⭐⭐⭐ 5", callback_data=f"rate_{order_id}_{courier_id}_5")]
    ])
    await bot.send_message(client_id, "Оцените работу курьера:", reply_markup=kb)

@dp.callback_query(F.data.startswith("rate_"))
async def process_review(callback: CallbackQuery):
    _, order_id, courier_id, rating = callback.data.split("_")
    await add_review(int(order_id), int(courier_id), int(rating), "Без комментария")
    await callback.message.edit_text("Спасибо за ваш отзыв! 🙏")

# bot.py

@dp.message(Command("stats"))
async def show_stats(message: Message):
    # Проверка на то, является ли пользователь админом (из конфига)
    if message.from_user.id != ADMIN_ID:
        return 

    stats = await get_stats_data()
    
    if stats:
        await message.answer(
            f"📊 **Статистика работы:**\n\n"
            f"✅ Всего заказов: {stats['total_orders']}\n"
            f"⭐ Средний рейтинг: {round(stats['avg_rating'] or 0, 2)}"
        )
    else:
        await message.answer("Статистики пока нет.")

# bot.py

@dp.message(Command("start"))
async def start(message: Message):
    # Кнопки выбора языка
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text="🇷🇴 Română", callback_data="lang_ro")]
    ])
    await message.answer("Выберите язык / Alegeți limba:", reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def set_lang(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    await set_user_lang(callback.from_user.id, lang)
    
    # После выбора языка показываем выбор роли на нужном языке
    text = get_text('welcome', lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('client', lang), callback_data="role_client")],
        [InlineKeyboardButton(text=get_text('courier', lang), callback_data="role_courier")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def send_localized_message(message: Message, key: str, **kwargs):
    # Получаем язык пользователя из БД
    lang = await get_user_lang(message.from_user.id)
    text = get_text(key, lang)
    await message.answer(text.format(**kwargs))

async def main():
    await connect_db()
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
