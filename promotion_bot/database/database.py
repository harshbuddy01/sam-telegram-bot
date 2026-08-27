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
            # Group migrations (per-account groups + selection + real chat_id)
            ("target_groups", "account_id", "INTEGER"),
            ("target_groups", "is_selected", "BOOLEAN DEFAULT 1"),
            ("target_groups", "chat_id", "BIGINT"),          # ← was missing — caused duplicate rows on every sync
            ("target_groups", "is_joined", "BOOLEAN DEFAULT 0"),
            # SenderAccount migrations (daily join tracking)
            ("sender_accounts", "joins_today", "INTEGER DEFAULT 0"),
            ("sender_accounts", "last_join_reset", "DATETIME"),
        ]
        for tbl, col, col_type in migrations:
            try:
                await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}"))
            except Exception:
                pass  # Column already exists — safe to ignore

        # ── Legacy cleanup ────────────────────────────────────────────────────
        # Delete all groups that were imported as plain text identifiers
        # (no real chat_id) — these are old garbage entries from pre-API sync.
        # After this runs, only groups synced directly from the Telegram API
        # (with a real chat_id) remain. The user can re-sync via 🔄 Sync button.
        try:
            await conn.execute(text(
                "DELETE FROM target_groups WHERE chat_id IS NULL"
            ))
        except Exception:
            pass

        # If there are still groups with NULL account_id, link to primary account
        try:
            res = await conn.execute(text("SELECT id FROM sender_accounts ORDER BY id ASC LIMIT 1"))
            first_acc = res.fetchone()
            if first_acc:
                first_acc_id = first_acc[0]
                await conn.execute(text(
                    f"UPDATE target_groups SET account_id = {first_acc_id} WHERE account_id IS NULL"
                ))
        except Exception:
            pass

