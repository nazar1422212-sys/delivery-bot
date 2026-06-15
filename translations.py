# translations.py

messages = {
    'ru': {
        'welcome': "Добро пожаловать! Выберите язык / Bun venit! Alegeți limba:",
        'client': "Я Клиент",
        'courier': "Я Курьер",
        'order_created': "✅ Заказ создан! Стоимость: 50 лей.",
        'cancel': "❌ Отменить"
    },
    'ro': {
        'welcome': "Bun venit! Alegeți limba / Добро пожаловать! Выберите язык:",
        'client': "Sunt Client",
        'courier': "Sunt Curier",
        'order_created': "✅ Comanda a fost creată! Preț: 50 lei.",
        'cancel': "❌ Anulează"
    }
}

def get_text(key, lang):
    return messages.get(lang, messages['ru']).get(key, key)
