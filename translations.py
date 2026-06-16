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
        'cancel': "❌ Отменить"
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
        'cancel': "❌ Anulează"
    }
}
messages['md'] = messages['ro']

def get_text(key, lang, **kwargs):
    text = messages.get(lang, messages['ru']).get(key, key)
    return text.format(**kwargs)
