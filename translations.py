messages = {
    'ru': {
        'welcome': "Добро пожаловать! Выберите роль:",
        'client': "Я Клиент",
        'courier': "Я Курьер",
        'choose_transport': "Выберите тип транспорта:",
        'standard': "🚗 Стандарт (30-100 лей)",
        'cargo': "🚚 Грузовой (200-600 лей)",
        'enter_phone': "📞 Введите номер телефона:",
        'order_created': "✅ Заказ №{id} создан! Цена: {price} лей.",
        'cancel': "❌ Отменить",
        'at_pickup_notify': "🚗 Курьер прибыл на место погрузки!",
        'delivery_done': "🎉 Заказ доставлен!",
        'client_ok': "✅ Хорошо",
        'order_accepted': "✅ Заказ №{id} принят!",
        'order_cancelled': "🚫 Заказ отменен.",
        'courier_warning': "⚠️ Клиент не подтвердил прибытие. Можете оставить заказ себе."
    },
    'ro': {
        'welcome': "Bun venit! Alegeți rolul:",
        'client': "Sunt Client",
        'courier': "Sunt Curier",
        'choose_transport': "Alegeți tipul de transport:",
        'standard': "🚗 Standard (30-100 lei)",
        'cargo': "🚚 Cargo (200-600 lei)",
        'enter_phone': "📞 Introduceți numărul de telefon:",
        'order_created': "✅ Comanda nr. {id} a fost creată! Preț: {price} lei.",
        'cancel': "❌ Anulează",
        'at_pickup_notify': "🚗 Curierul a ajuns la punctul de preluare!",
        'delivery_done': "🎉 Comanda a fost livrată!",
        'client_ok': "✅ Bine",
        'order_accepted': "✅ Comanda nr. {id} a fost acceptată!",
        'order_cancelled': "🚫 Comanda a fost anulată.",
        'courier_warning': "⚠️ Clientul nu a confirmat sosirea. Puteți păstra comanda."
    }
}

# Добавляем молдавский как алиас к румынскому
messages['md'] = messages['ro']

def get_text(key, lang, **kwargs):
    """
    Получает текст по ключу и языку, подставляя аргументы.
    Пример: get_text('order_created', 'ru', id=123, price=50)
    """
    # Получаем словарь языка, по умолчанию ру
    lang_data = messages.get(lang, messages['ru'])
    # Получаем текст, если ключ не найден - возвращаем сам ключ
    text = lang_data.get(key, key)
    
    # Если переданы аргументы для форматирования, подставляем их
    if kwargs:
        return text.format(**kwargs)
    return text
