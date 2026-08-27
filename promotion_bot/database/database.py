import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import config
from database.models import Base

logger = logging.getLogger(__name__)

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
            ("promo_messages", "is_enabled", "BOOLEAN DEFAULT 0"),
            ("promo_messages", "status", "VARCHAR(50) DEFAULT 'IDLE'"),
            ("promo_messages", "last_run_at", "DATETIME"),
            # BroadcastCycle migrations
            ("broadcast_cycles", "account_id", "INTEGER"),
            ("broadcast_cycles", "account_phone", "VARCHAR(50)"),
            # Group migrations (per-account groups + selection + real chat_id)
            ("target_groups", "account_id", "INTEGER"),
            ("target_groups", "is_selected", "BOOLEAN DEFAULT 1"),
            ("target_groups", "chat_id", "BIGINT"),
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

        # ── Remove legacy UNIQUE constraint on target_groups.identifier ────────
        # Old schema had `identifier UNIQUE`, which causes crashes when multiple accounts
        # sync the same groups or when syncing large dialog lists.
        try:
            res = await conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='target_groups'"))
            table_def = res.fetchone()
            if table_def and table_def[0] and "UNIQUE" in table_def[0].upper():
                logger.info("Rebuilding target_groups to remove outdated global UNIQUE constraint...")
                await conn.execute(text("PRAGMA foreign_keys=OFF;"))
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS target_groups_clean (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER,
                        chat_id BIGINT,
                        title VARCHAR(255),
                        identifier VARCHAR(255) NOT NULL,
                        is_joined BOOLEAN DEFAULT 0,
                        is_selected BOOLEAN DEFAULT 1,
                        status VARCHAR(50) DEFAULT 'ACTIVE',
                        last_sent_at DATETIME,
                        last_error TEXT,
                        failure_count INTEGER DEFAULT 0,
                        consecutive_failures INTEGER DEFAULT 0,
                        slowmode_seconds INTEGER DEFAULT 0,
                        created_at DATETIME,
                        updated_at DATETIME
                    );
                """))
                await conn.execute(text("""
                    INSERT OR IGNORE INTO target_groups_clean
                    (id, account_id, chat_id, title, identifier, is_joined, is_selected, status, last_sent_at, last_error, failure_count, consecutive_failures, slowmode_seconds, created_at, updated_at)
                    SELECT id, account_id, chat_id, title, identifier, is_joined, is_selected, status, last_sent_at, last_error, failure_count, consecutive_failures, slowmode_seconds, created_at, updated_at
                    FROM target_groups;
                """))
                await conn.execute(text("DROP TABLE target_groups;"))
                await conn.execute(text("ALTER TABLE target_groups_clean RENAME TO target_groups;"))
                await conn.execute(text("PRAGMA foreign_keys=ON;"))
                logger.info("target_groups table rebuilt cleanly.")
        except Exception as ex:
            logger.warning(f"target_groups table rebuild check: {ex}")

        # Link any orphaned groups (account_id IS NULL) to first account
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


