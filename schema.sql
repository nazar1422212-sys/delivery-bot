CREATE TABLE IF NOT EXISTS users(
    tg_id BIGINT PRIMARY KEY,
    username TEXT,
    role TEXT,
    phone TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS couriers(
    tg_id BIGINT PRIMARY KEY,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    online BOOLEAN DEFAULT TRUE,
    rating DOUBLE PRECISION DEFAULT 5
);

CREATE TABLE IF NOT EXISTS states(
    tg_id BIGINT PRIMARY KEY,
    state TEXT,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS orders(
    id SERIAL PRIMARY KEY,

    client_id BIGINT,
    courier_id BIGINT,

    pickup_lat DOUBLE PRECISION,
    pickup_lon DOUBLE PRECISION,

    delivery_lat DOUBLE PRECISION,
    delivery_lon DOUBLE PRECISION,

    distance DOUBLE PRECISION,
    price DOUBLE PRECISION,

    status TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ratings(
    id SERIAL PRIMARY KEY,
    courier_id BIGINT,
    stars INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
-- Добавить в таблицу couriers
ALTER TABLE couriers ADD COLUMN passport_url TEXT;
ALTER TABLE couriers ADD COLUMN is_verified BOOLEAN DEFAULT FALSE;

-- Таблица для истории заказов уже частично есть, добавим поле для финальной стоимости и статуса оплаты
ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'pending'; -- 'paid', 'cash'
