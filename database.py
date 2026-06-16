import asyncpg
import logging
import aiofiles
from config import DATABASE_URL

logger = logging.getLogger(__name__)

pool = None

async def connect_db():
    """Create database connection pool"""
    global pool
    try:
        pool = await asyncpg.create_pool(
            DATABASE_URL, 
            min_size=1, 
            max_size=10,
            command_timeout=60
        )
        logger.info("Database connection pool created")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

async def _ensure_pool():
    """Ensure pool is initialized"""
    if pool is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")

async def execute(query, *args):
    """Execute a query without returning results"""
    await _ensure_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)

async def fetch(query, *args):
    """Fetch multiple rows"""
    await _ensure_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)

async def fetchval(query, *args):
    """Fetch a single value"""
    await _ensure_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)

async def init_db():
    """Initialize database - run schema if needed"""
    try:
        await _ensure_pool()
        # Use async file reading
        async with aiofiles.open('schema.sql', mode='r') as f:
            schema = await f.read()
        
        async with pool.acquire() as conn:
            await conn.execute(schema)
        logger.info("Database schema initialized")
    except FileNotFoundError:
        logger.error("schema.sql not found")
        raise
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

# --- ORDER FUNCTIONS ---

async def create_order(client_tg_id, pickup_addr, delivery_addr, price, method, phone, vehicle_type, p_lat=None, p_lon=None, d_lat=None, d_lon=None):
    """Create a new order"""
    try:
        query = """
            INSERT INTO orders (client_tg_id, pickup_address, delivery_address, price, payment_method, 
                                client_phone, vehicle_type, pickup_lat, pickup_lon, delivery_lat, delivery_lon)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
        """
        order_id = await fetchval(query, client_tg_id, pickup_addr, delivery_addr, price, method, phone, vehicle_type, p_lat, p_lon, d_lat, d_lon)
        logger.info(f"Order created: {order_id}")
        return order_id
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        return None

async def get_order_data(order_id):
    """Get order details by ID"""
    try:
        row = await fetch("SELECT * FROM orders WHERE id = $1", int(order_id))
        if row:
            return dict(row[0])
        return None
    except Exception as e:
        logger.error(f"Error fetching order: {e}")
        return None

async def get_waiting_orders():
    """Get all orders waiting for a courier"""
    try:
        rows = await fetch("SELECT * FROM orders WHERE status = 'waiting' ORDER BY created_at ASC")
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching waiting orders: {e}")
        return []

async def update_order_status(order_id, status, courier_id=None):
    """Update order status"""
    try:
        if courier_id:
            await execute("UPDATE orders SET status = $1, courier_id = $2 WHERE id = $3", status, courier_id, int(order_id))
        else:
            await execute("UPDATE orders SET status = $1 WHERE id = $2", status, int(order_id))
        logger.info(f"Order {order_id} status updated to {status}")
    except Exception as e:
        logger.error(f"Error updating order status: {e}")

async def get_my_active_order(courier_tg_id):
    """Get active order for a courier"""
    try:
        row = await fetch("SELECT * FROM orders WHERE courier_id = $1 AND status IN ('in_progress', 'at_pickup')", courier_tg_id)
        if row:
            return dict(row[0])
        return None
    except Exception as e:
        logger.error(f"Error fetching active order: {e}")
        return None

async def cancel_order_db(order_id):
    """Cancel an order"""
    try:
        await execute("DELETE FROM orders WHERE id = $1 AND status IN ('waiting', 'pending')", int(order_id))
        logger.info(f"Order {order_id} cancelled")
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")

# --- USER AND COURIER FUNCTIONS ---

async def set_user_role(tg_id, role):
    """Set or update user role"""
    try:
        await execute("INSERT INTO users (tg_id, role) VALUES ($1, $2) ON CONFLICT (tg_id) DO UPDATE SET role = $2", tg_id, role)
        logger.info(f"User {tg_id} role set to {role}")
    except Exception as e:
        logger.error(f"Error setting user role: {e}")

async def set_user_lang(tg_id, lang):
    """Set user language preference"""
    try:
        await execute("UPDATE users SET lang = $1 WHERE tg_id = $2", lang, tg_id)
    except Exception as e:
        logger.error(f"Error setting user language: {e}")

async def get_user_lang(tg_id):
    """Get user language preference"""
    try:
        row = await fetchval("SELECT lang FROM users WHERE tg_id = $1", tg_id)
        return row if row else 'ru'
    except Exception as e:
        logger.error(f"Error fetching user language: {e}")
        return 'ru'

async def get_verified_couriers():
    """Get all verified and online couriers"""
    try:
        rows = await fetch("SELECT tg_id FROM couriers WHERE is_verified = TRUE AND online = TRUE")
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching verified couriers: {e}")
        return []

async def create_courier(tg_id):
    """Create or register a courier"""
    try:
        await execute("INSERT INTO couriers (tg_id) VALUES ($1) ON CONFLICT (tg_id) DO NOTHING", tg_id)
        logger.info(f"Courier {tg_id} created")
    except Exception as e:
        logger.error(f"Error creating courier: {e}")

async def update_courier_location(tg_id, lat, lon):
    """Update courier location"""
    try:
        await execute("UPDATE couriers SET lat = $1, lon = $2 WHERE tg_id = $3", lat, lon, tg_id)
    except Exception as e:
        logger.error(f"Error updating courier location: {e}")

async def set_courier_online(tg_id, online):
    """Set courier online status"""
    try:
        await execute("UPDATE couriers SET online = $1 WHERE tg_id = $2", online, tg_id)
        logger.info(f"Courier {tg_id} online status: {online}")
    except Exception as e:
        logger.error(f"Error setting courier online status: {e}")

async def get_courier_data(tg_id):
    """Get courier profile data"""
    try:
        row = await fetch("SELECT * FROM couriers WHERE tg_id = $1", tg_id)
        if row:
            return dict(row[0])
        return None
    except Exception as e:
        logger.error(f"Error fetching courier data: {e}")
        return None

async def close_pool():
    """Close database connection pool"""
    global pool
    if pool:
        await pool.close()
        logger.info("Database connection pool closed")
