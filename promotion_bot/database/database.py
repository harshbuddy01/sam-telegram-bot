import logging
import datetime
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

from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    async with engine.begin() as conn:
        # Create all tables defined in models (safe, won't touch existing tables)
        await conn.run_sync(Base.metadata.create_all)

        # ── Safe column migrations (never destructive) ─────────────────────────
        migrations = [
            ("promo_messages", "account_id",    "INTEGER"),
            ("promo_messages", "interval_hours", "FLOAT DEFAULT 2.0"),
            ("promo_messages", "is_enabled",     "BOOLEAN DEFAULT 0"),
            ("promo_messages", "status",         "VARCHAR(50) DEFAULT 'IDLE'"),
            ("promo_messages", "last_run_at",    "DATETIME"),
            ("promo_messages", "saved_msg_id",   "INTEGER"),
            ("broadcast_cycles", "account_id",   "INTEGER"),
            ("broadcast_cycles", "account_phone","VARCHAR(50)"),
            ("target_groups",  "account_id",     "INTEGER"),
            ("target_groups",  "is_selected",    "BOOLEAN DEFAULT 1"),
            ("target_groups",  "chat_id",        "BIGINT"),
            ("target_groups",  "is_joined",      "BOOLEAN DEFAULT 0"),
            ("sender_accounts","joins_today",     "INTEGER DEFAULT 0"),
            ("sender_accounts","last_join_reset", "DATETIME"),
        ]
        for tbl, col, col_type in migrations:
            try:
                await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}"))
            except Exception:
                pass  # Column already exists — safe to ignore

        # ── Safe column migrations complete ─────────────────────────────────

        # ── FIX: Repair any inverted HTML tags from old emoji extractor ───────
        try:
            res = await conn.execute(text("SELECT id, text FROM promo_messages"))
            rows = res.fetchall()
            for row_id, p_text in rows:
                if p_text and isinstance(p_text, str):
                    fixed = p_text.replace("</b></u>", "</u></b>").replace("</i></u>", "</u></i>").replace("</u></code>", "</code></u>")
                    if fixed != p_text:
                        await conn.execute(text("UPDATE promo_messages SET text = :t WHERE id = :id"), {"t": fixed, "id": row_id})
        except Exception as ex:
            logger.warning(f"Could not sanitize promo_messages text: {ex}")

        # ── FIX: Restore any groups falsely restricted by ResolveUsernameRequest flood wait ─
        try:
            await conn.execute(text("""
                UPDATE target_groups 
                SET status = 'ACTIVE', last_error = NULL, failure_count = 0, consecutive_failures = 0
                WHERE last_error LIKE '%ResolveUsernameRequest%'
            """))
        except Exception as ex:
            logger.warning(f"Could not restore groups: {ex}")

        # ── Drop any UNIQUE index on target_groups (e.g. ix_target_groups_identifier) ──
        try:
            res_idx = await conn.execute(text(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='target_groups'"
            ))
            indexes = res_idx.fetchall()
            for idx_name, idx_sql in indexes:
                if idx_sql and "UNIQUE" in idx_sql.upper():
                    logger.info(f"Dropping unique index {idx_name} on target_groups: {idx_sql}")
                    await conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
        except Exception as ex_idx:
            logger.warning(f"Could not drop unique index: {ex_idx}")

        # ── SAFE table rebuild: ensure target_groups has NO UNIQUE constraint ─
        try:
            res = await conn.execute(text(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='target_groups'"
            ))
            table_def = res.fetchone()
            has_unique = table_def and table_def[0] and "UNIQUE" in table_def[0].upper()

            if has_unique:
                logger.info("Rebuilding target_groups table to remove UNIQUE constraint...")
                await conn.execute(text("PRAGMA foreign_keys=OFF"))
                await conn.execute(text("DROP TABLE IF EXISTS target_groups_clean"))
                await conn.execute(text("""
                    CREATE TABLE target_groups_clean (
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
                    )
                """))
                await conn.execute(text("""
                    INSERT INTO target_groups_clean
                        (id, account_id, chat_id, title, identifier, is_joined, is_selected,
                         status, last_sent_at, last_error, failure_count, consecutive_failures,
                         slowmode_seconds, created_at, updated_at)
                    SELECT id, account_id, chat_id, title, identifier, is_joined, is_selected,
                         status, last_sent_at, last_error, failure_count, consecutive_failures,
                         slowmode_seconds, created_at, updated_at
                    FROM target_groups
                """))
                await conn.execute(text("DROP TABLE target_groups"))
                await conn.execute(text("ALTER TABLE target_groups_clean RENAME TO target_groups"))
                await conn.execute(text("PRAGMA foreign_keys=ON"))
                logger.info("target_groups rebuilt without UNIQUE constraint.")
        except Exception as ex:
            logger.warning(f"target_groups rebuild check: {ex}")

        # ── Link orphaned groups (account_id IS NULL) to first account ───────
        try:
            res = await conn.execute(text(
                "SELECT id FROM sender_accounts ORDER BY id ASC LIMIT 1"
            ))
            first_acc = res.fetchone()
            if first_acc:
                await conn.execute(text(
                    f"UPDATE target_groups SET account_id = {first_acc[0]} WHERE account_id IS NULL"
                ))
        except Exception:
            pass
