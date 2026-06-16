-- 1. Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    tg_id BIGINT PRIMARY KEY,
    username TEXT,
    role TEXT,
    phone TEXT,
    lang TEXT DEFAULT 'ru',
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. Таблица курьеров
CREATE TABLE IF NOT EXISTS couriers (
    tg_id BIGINT PRIMARY KEY,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    online BOOLEAN DEFAULT TRUE,
    rating DOUBLE PRECISION DEFAULT 5,
    passport_url TEXT,
    is_verified BOOLEAN DEFAULT FALSE
);

-- 3. Таблица состояний FSM
CREATE TABLE IF NOT EXISTS states (
    tg_id BIGINT PRIMARY KEY,
    state TEXT,
    payload TEXT
);

-- 4. Таблица заказов (полная структура)
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    client_tg_id BIGINT,
    courier_id BIGINT,
    
    pickup_address TEXT,
    delivery_address TEXT,
    
    pickup_lat DOUBLE PRECISION,
    pickup_lon DOUBLE PRECISION,
    delivery_lat DOUBLE PRECISION,
    delivery_lon DOUBLE PRECISION,
    
    price DOUBLE PRECISION,
    vehicle_type TEXT DEFAULT 'standard',
    client_phone TEXT,
    
    status TEXT DEFAULT 'waiting',
    payment_status TEXT DEFAULT 'pending',
    payment_method TEXT,
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. Таблица рейтингов
CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    courier_id BIGINT,
    stars INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 6. Таблица истории заказов
CREATE TABLE IF NOT EXISTS order_history (
    id SERIAL PRIMARY KEY,
    order_id INT,
    courier_id BIGINT,
    price DOUBLE PRECISION,
    rating INT,
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
