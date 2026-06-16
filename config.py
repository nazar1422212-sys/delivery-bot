import os

TOKEN = os.getenv("TOKEN") 
DATABASE_URL = os.getenv("DATABASE_URL")

PRICE_PER_KM = 10
ADMIN_ID = 8800119191  # Your ID without quotes and list

# Validate required environment variables
if not TOKEN:
    raise ValueError("TOKEN environment variable is not set")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")
