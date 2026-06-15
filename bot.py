import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from translations import get_text
from database import get_user_lang
import keep_alive.py
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
    payment_method = State()

# --- Логика Ролей ---
@dp.message(Command("start"))
async def start(message: Message):
    lang = await get_user_lang(message.from_user.id)
    
    # Кнопки также должны быть локализованы
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
    await state.update_data(delivery=message.text)
    
    # Создаем клавиатуру выбора
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Наличные", callback_data="pay_cash")],
        [InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")]
    ])
    
    await message.answer("Выберите способ оплаты:", reply_markup=kb)
    await state.set_state(OrderForm.payment_method)

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

# Универсальная функция для отправки сообщений на языке пользователя
async def send_msg(message, key, reply_markup=None):
    # Получаем язык пользователя из БД (по умолчанию 'ru', если не нашли)
    lang = await get_user_lang(message.from_user.id)
    text = get_text(key, lang)
    await message.answer(text, reply_markup=reply_markup)

@dp.message(OrderForm.delivery)
async def process_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    # Создаем заказ сразу со статусом 'waiting'
    order = await create_order(message.from_user.id, data['pickup'], message.text, 50.0)
    
    couriers = await get_verified_couriers()
    
    if not couriers:
        # Если курьеров нет, сообщаем об ожидании
        await message.answer("❌ Свободных курьеров нет. Ваш заказ в очереди на поиск...")
        await set_order_waiting(order['id'])
    else:
        # Рассылка курьерам (как мы делали раньше)
        ...

# bot.py

async def check_queue():
    while True:
        # Ищем заказы, которые ждут курьера
        orders = await get_waiting_orders()
        for order in orders:
            # Если есть хоть один онлайн курьер, отправляем ему заказ
            couriers = await get_verified_couriers() 
            if couriers:
                for c in couriers:
                    # Уведомляем курьера о заказе из очереди
                    await bot.send_message(c['tg_id'], f"🔔 Появился заказ №{order['id']} из очереди!")
                # Обновляем статус, чтобы не спамить
                await update_order_status(order['id'], 'pending')
        
        await asyncio.sleep(30) # Пауза 30 секунд между проверками

# bot.py

# bot.py

@dp.message(Command("history"))
async def show_history(message: Message):
    history = await get_courier_history(message.from_user.id)
    
    if not history:
        await message.answer("У вас пока нет выполненных заказов.")
        return

    text = "📜 **Ваши последние доходы:**\n\n"
    total_earned = 0
    
    for row in history:
        text += f"📦 Заказ №{row['order_id']} | 💰 {row['price']} лей | { '⭐'*row['rating'] if row['rating'] else 'Нет оценки' }\n"
        total_earned += row['price']
    
    text += f"\n📊 **Итого заработано: {total_earned} лей**"
    await message.answer(text)

# Пример в bot.py
async def finish_order_logic(order_id, courier_id, price):
    # 1. Меняем статус в базе
    await update_order_status(order_id, 'finished')
    
    # 2. Добавляем в историю с ценой (рейтинг пока 0)
    await add_review(order_id, courier_id, price, 0, "Заказ завершен")

async def main():
    await connect_db()
    await init_db()
    await dp.start_polling(bot)

@dp.callback_query(OrderForm.payment_method, F.data.startswith("pay_"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1]
    data = await state.get_data()
    
    # Сохраняем метод оплаты в базу (через вашу функцию create_order)
    # Предполагаем, что функция create_order принимает payment_method
    await create_order(
        user_id=callback.from_user.id,
        pickup=data['pickup'],
        delivery=data['delivery'],
        payment_method=method
    )
    
    text = "✅ Заказ создан! Оплата: " + ("Наличными" if method == 'cash' else "Картой")
    await callback.message.edit_text(text)
    await state.clear()

if __name__ == "__main__":
    asyncio.run(main())
