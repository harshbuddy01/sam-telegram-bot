from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import config
from database.models import Base

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


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Safe SQLite column migrations for existing databases
        migrations = [
            # PromoMessage migrations
            ("promo_messages", "account_id", "INTEGER"),
            ("promo_messages", "interval_hours", "FLOAT DEFAULT 2.0"),
            ("promo_messages", "is_enabled", "BOOLEAN DEFAULT 1"),
            ("promo_messages", "status", "VARCHAR(50) DEFAULT 'IDLE'"),
            ("promo_messages", "last_run_at", "DATETIME"),
            # BroadcastCycle migrations
            ("broadcast_cycles", "account_id", "INTEGER"),
            ("broadcast_cycles", "account_phone", "VARCHAR(50)"),
            # Group migrations (per-account groups + selection)
            ("target_groups", "account_id", "INTEGER"),
            ("target_groups", "is_selected", "BOOLEAN DEFAULT 1"),
            # SenderAccount migrations (daily join tracking)
            ("sender_accounts", "joins_today", "INTEGER DEFAULT 0"),
            ("sender_accounts", "last_join_reset", "DATETIME"),
        ]
        for tbl, col, col_type in migrations:
            try:
                await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}"))
            except Exception:
                pass  # Column already exists
