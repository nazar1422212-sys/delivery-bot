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
from database import cancel_order_db
from database import get_order_courier
from geopy.distance import geodesic

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

# 1. Добавьте этот обработчик в ваш bot.py
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    
    # Вызываем функцию отмены из базы данных
    await cancel_order_db(order_id)
    
    # Обновляем сообщение для клиента
    await callback.message.edit_text("❌ Заказ был успешно отменен.")
    await callback.answer("Заказ отменен")

# 2. Обновите функцию создания заказа (process_delivery), 
# чтобы она отправляла кнопку отмены:
@dp.message(OrderForm.delivery, F.location)
async def process_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    p_lat, p_lon = data['pickup']
    # ... ваш код создания заказа ...
    order = await create_order(message.from_user.id, p_lat, p_lon, message.location.latitude, message.location.longitude, 5.0)
    
    # Кнопка отмены
    kb_cancel = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_{order['id']}")]
    ])
    
    await message.answer(f"✅ Заказ создан! Стоимость: {order['price']} лей.", reply_markup=kb_cancel)
    await state.clear()
    
    # ... уведомление курьеров ...

# ... (здесь импорты и все обработчики @dp.message ...)

# Добавьте этот код в ваш bot.py
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    
    # 1. Проверяем, был ли назначен курьер
    courier_id = await get_order_courier(order_id)
    
    # 2. Отменяем в базе
    await cancel_order_db(order_id)
    
    # 3. Сообщаем клиенту
    await callback.message.edit_text("❌ Заказ был успешно отменен.")
    
    # 4. Если курьер был, уведомляем его вежливо
    if courier_id:
        try:
            await bot.send_message(
                courier_id, 
                f"⚠️ Заказ №{order_id} был отменен клиентом. Извините за неудобства."
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление курьеру: {e}")

    await callback.answer("Заказ отменен")

from translations import messages

# Функция для получения текста
def get_text(key, lang='ru'):
    return messages.get(lang, messages['ru']).get(key, key)

# Обработчик /start с выбором языка (или можно сделать команду /lang)
@dp.message(Command("start"))
async def start(message: Message):
    # Допустим, мы сохраняем язык в FSM или БД
    lang = 'ro' # Это можно получать из базы данных пользователя
    text = get_text('welcome', lang)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('client', lang), callback_data="role_client")],
        [InlineKeyboardButton(text=get_text('courier', lang), callback_data="role_courier")]
    ])
    await message.answer(text, reply_markup=kb)

# bot.py

# Генерация ссылки для Google Maps
def get_maps_link(p_lat, p_lon, d_lat, d_lon):
    return f"https://www.google.com/maps/dir/?api=1&origin={p_lat},{p_lon}&destination={d_lat},{d_lon}&travelmode=driving"

# Курьер отправляет свою геопозицию
@dp.message(F.location)
async def update_location(message: Message):
    # Предполагаем, что курьер прислал геолокацию
    await update_courier_location(message.from_user.id, message.location.latitude, message.location.longitude)
    await message.answer("📍 Ваша локация обновлена в системе.")

# При рассылке заказа курьерам (в функции process_delivery)
# ...
link = get_maps_link(p_lat, p_lon, message.location.latitude, message.location.longitude)
kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{order['id']}")],
    [InlineKeyboardButton(text="🗺 Навигация", url=link)]
])
# Рассылаем только ближайшим (из get_nearest_couriers)


@dp.callback_query(F.data.startswith("arrived_"))
async def check_arrival(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    # Получаем координаты клиента из БД (нужно добавить функцию получения координат заказа)
    order_coords = await get_order_coords(order_id) 
    courier_coords = await get_courier_coords(callback.from_user.id)
    
    distance = geodesic(order_coords, courier_coords).meters
    
    if distance <= 100:
        await update_order_status(order_id, 'arrived')
        await callback.message.edit_text("✅ Отлично! Вы прибыли к клиенту.")
    else:
        await callback.answer(f"❌ Вы еще далеко ({int(distance)} м)", show_alert=True)

# Когда курьер нажимает "Доставлено"
@dp.callback_query(F.data.startswith("delivered_"))
async def confirm_delivery(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    # Уведомляем клиента, чтобы он подтвердил получение
    await bot.send_message(client_id, f"Курьер отмечает заказ №{order_id} как доставленный. Вы получили заказ?")
    # Кнопка для клиента: "Да, всё получено"

async def main():
    await connect_db()
    await init_db()  # <-- ВОТ ЗДЕСЬ ОНО ДОЛЖНО БЫТЬ!
    print("База данных инициализирована.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
