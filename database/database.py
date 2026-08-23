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
            "ALTER TABLE orders ADD COLUMN status VARCHAR(30) DEFAULT 'COMPLETED'",
            "ALTER TABLE orders ADD COLUMN customer_input TEXT",
            "ALTER TABLE orders ADD COLUMN fulfilled_at DATETIME",
            "ALTER TABLE deposits ADD COLUMN gateway VARCHAR(50) DEFAULT 'MANUAL_UPI'",
            "ALTER TABLE deposits ADD COLUMN gateway_order_id VARCHAR(100)",
            "ALTER TABLE deposits ADD COLUMN gateway_payment_id VARCHAR(100)",
        ]
        for query in migrations:
            try:
                await conn.execute(text(query))
            except Exception:
                pass # Column already exists
