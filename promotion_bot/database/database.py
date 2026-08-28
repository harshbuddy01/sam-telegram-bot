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

        # ── FIX: Force-disable scheduler for ALL existing accounts ────────────
        # Old code created promo_messages with is_enabled=1 as default.
        # SQLite ALTER TABLE DEFAULT only affects NEW rows, not existing ones.
        # So we must explicitly UPDATE all existing rows to turn scheduler OFF.
        # Users must go to ⏰ Scheduler and tap "Enable" to re-activate per account.
        try:
            now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            await conn.execute(text(
                "UPDATE promo_messages SET is_enabled = 0, last_run_at = :now WHERE 1=1"
            ), {"now": now_str})
        except Exception as ex:
            logger.warning(f"Could not update promo_messages scheduler state: {ex}")

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

        # ── SAFE table rebuild: remove UNIQUE constraint on target_groups.identifier
        # The old schema had identifier UNIQUE globally — this crashes multi-account sync.
        # We rebuild ONLY if UNIQUE is detected AND target_groups_clean does NOT yet exist.
        try:
            res = await conn.execute(text(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='target_groups'"
            ))
            table_def = res.fetchone()
            has_unique = table_def and table_def[0] and "UNIQUE" in table_def[0].upper()

            # Check if target_groups_clean already exists (from a previous failed run)
            res2 = await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='target_groups_clean'"
            ))
            clean_exists = res2.fetchone() is not None

            if has_unique and not clean_exists:
                logger.info("Rebuilding target_groups table to remove UNIQUE constraint...")
                await conn.execute(text("PRAGMA foreign_keys=OFF"))
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
            elif clean_exists:
                # A previous rebuild was interrupted — finish it
                try:
                    await conn.execute(text("DROP TABLE IF EXISTS target_groups"))
                    await conn.execute(text("ALTER TABLE target_groups_clean RENAME TO target_groups"))
                    logger.info("Completed interrupted target_groups rebuild.")
                except Exception:
                    pass

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
