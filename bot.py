import asyncio
import keep_alive
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from translations import get_text
from config import TOKEN, ADMIN_ID
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from database import (
    connect_db, init_db, set_user_role, update_courier_verification, 
    get_verified_couriers, update_order_status, create_order, 
    cancel_order_db, get_order_courier, get_user_lang, set_user_lang,
    set_passport_photo, verify_courier, delete_inactive_couriers, 
    update_courier_activity, set_courier_status, get_waiting_orders,
    set_order_waiting, create_courier
)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

class OrderForm(StatesGroup):
    pickup = State()
    delivery = State()
    payment_method = State()

@dp.message(Command("start"))
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"), InlineKeyboardButton(text="🇷🇴 Română", callback_data="lang_ro")]
    ])
    await message.answer("Выберите язык / Alegeți limba:", reply_markup=kb)

@dp.callback_query(F.data.startswith("lang_"))
async def set_lang(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    await set_user_lang(callback.from_user.id, lang)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('client', lang), callback_data="role_client")],
        [InlineKeyboardButton(text=get_text('courier', lang), callback_data="role_courier")]
    ])
    await callback.message.edit_text(get_text('welcome', lang), reply_markup=kb)

@dp.callback_query(F.data.startswith("role_"))
async def set_role(callback: CallbackQuery):
    role = callback.data.split("_")[1]
    await set_user_role(callback.from_user.id, role)
    
    # Create courier record if role is courier
    if role == "courier":
        await create_courier(callback.from_user.id)
    
    await callback.message.answer(f"✅ Зарегистрированы как {role}")

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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Наличные", callback_data="pay_cash"), InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")]
    ])
    await message.answer("Выберите способ оплаты:", reply_markup=kb)
    await state.set_state(OrderForm.payment_method)

@dp.callback_query(OrderForm.payment_method, F.data.startswith("pay_"))
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    # 1. ОБЯЗАТЕЛЬНО отвечаем на колбэк, чтобы убрать "зависание" кнопки
    await callback.answer() 
    
    method = callback.data.split("_")[1]
    data = await state.get_data()
    
    # 2. Создаем заказ в БД
    order_id = await create_order(callback.from_user.id, data['pickup'], data['delivery'], 50.0, method)
    
    if order_id:
        await set_order_waiting(order_id)
        
        # 3. Сообщаем пользователю
        await callback.message.edit_text(f"✅ Заказ №{order_id} создан и поставлен в очередь!")
    else:
        await callback.message.edit_text("❌ Ошибка при создании заказа. Попробуйте позже.")
    
    # 4. ОЧИЩАЕМ состояние FSM, чтобы бот вернулся в обычный режим
    await state.clear()

@dp.message(F.photo)
async def handle_passport(message: Message):
    photo_id = message.photo[-1].file_id
    await set_passport_photo(message.from_user.id, photo_id)
    await bot.send_photo(
        ADMIN_ID, 
        photo_id, 
        caption=f"🛂 Курьер {message.from_user.id} прислал паспорт. Одобрить?", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{message.from_user.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message.from_user.id}")
        ]])
    )
    await message.answer("✅ Паспорт получен. Ожидайте подтверждения.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_courier(callback: CallbackQuery):
    courier_id = callback.data.split("_")[1]
    await verify_courier(int(courier_id))
    await callback.message.edit_caption(caption=f"✅ Курьер {courier_id} одобрен!")
    await bot.send_message(int(courier_id), "🎉 Ваш аккаунт проверен! /online")

@dp.message(Command("online"))
async def go_online(message: Message):
    await set_courier_status(message.from_user.id, True)
    await update_courier_activity(message.from_user.id)
    await message.answer("✅ Вы онлайн!")

@dp.message(Command("offline"))
async def go_offline(message: Message):
    await set_courier_status(message.from_user.id, False)
    await update_courier_activity(message.from_user.id)
    await message.answer("💤 Вы ушли с линии.")

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer("🆘 *Помощь:*\n📦 /order - Заказ\n🚚 /online - Онлайн\n💤 /offline - Офлайн\n💳 /setcard - Карта")

async def check_queue():
    while True:
        orders = await get_waiting_orders()
        for order in orders:
            # orders - это список словарей/рядов из базы
            couriers = await get_verified_couriers()
            if couriers:
                # ВАЖНО: берем данные из объекта order
                text = (f"🔔 **Новый заказ №{order['id']}**\n"
                        f"📍 Откуда: {order['pickup_address']}\n"
                        f"🏁 Куда: {order['delivery_address']}\n"
                        f"💰 Цена: {order['price']} леев\n"
                        f"🗺 [Открыть в Google Maps](https://www.google.com/maps/search/?api=1&query={order['delivery_address'].replace(' ', '+')})")
                
                await bot.send_message(couriers[0]['tg_id'], text, parse_mode="Markdown")
                await update_order_status(order['id'], 'pending')
        await asyncio.sleep(60)


def get_distance(addr1, addr2):
    geolocator = Nominatim(user_agent="delivery_bot")
    try:
        loc1 = geolocator.geocode(addr1)
        loc2 = geolocator.geocode(addr2)
        return round(geodesic((loc1.latitude, loc1.longitude), (loc2.latitude, loc2.longitude)).km, 1)
    except:
        return "?" # Если адрес не найден

async def main():
    await connect_db()
    await init_db()
    keep_alive.run_web()
    asyncio.create_task(check_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
