import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
import config

engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
    future=True
)

from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def init_db():
    db_dir = os.path.dirname(os.path.abspath(config.DB_PATH))
    if db_dir:
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError:
            pass
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Safe column migrations for existing SQLite databases
        migrations = [
            "ALTER TABLE variants ADD COLUMN fulfillment_type VARCHAR(20) DEFAULT 'AUTOMATIC'",
            "ALTER TABLE variants ADD COLUMN manual_dispatch_time VARCHAR(50) DEFAULT '1–2 Hours'",
            "ALTER TABLE variants ADD COLUMN input_type VARCHAR(50) DEFAULT 'ANY'",
            "ALTER TABLE variants ADD COLUMN input_prompt TEXT",
            "ALTER TABLE variants ADD COLUMN stock_quantity INTEGER DEFAULT 50",
            "ALTER TABLE orders ADD COLUMN status VARCHAR(30) DEFAULT 'COMPLETED'",
            "ALTER TABLE orders ADD COLUMN customer_input TEXT",
            "ALTER TABLE orders ADD COLUMN fulfilled_at DATETIME",
            "ALTER TABLE deposits ADD COLUMN gateway VARCHAR(50) DEFAULT 'MANUAL_UPI'",
            "ALTER TABLE deposits ADD COLUMN gateway_order_id VARCHAR(100)",
            "ALTER TABLE deposits ADD COLUMN gateway_payment_id VARCHAR(100)",
            "ALTER TABLE deposits ADD COLUMN target_variant_id INTEGER",
            "UPDATE products SET title = REPLACE(title, '❤️', '') WHERE title LIKE '%❤️%'",
            "UPDATE categories SET name = REPLACE(name, '❤️', '') WHERE name LIKE '%❤️%'",
        ]
        for query in migrations:
            try:
                await conn.execute(text(query))
            except Exception:
                pass # Column already exists or already updated
