import re
import datetime
from sqlalchemy import select, update, delete, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Group, PromoMessage, BroadcastCycle, BroadcastLog, BotSetting, SenderAccount, JoinLog
import config

# ==================== SENDER ACCOUNTS ====================

async def add_or_update_sender_account(
    session: AsyncSession,
    phone: str,
    session_string: str,
    user_id: int = None,
    username: str = None,
    first_name: str = None,
    is_premium: bool = False,
    set_active: bool = True
) -> SenderAccount:
    clean_phone = phone.strip()
    result = await session.execute(select(SenderAccount).where(SenderAccount.phone == clean_phone))
    account = result.scalars().first()

    if set_active:
        await session.execute(update(SenderAccount).values(is_active=False))

    if account:
        account.session_string = session_string
        if user_id: account.user_id = user_id
        if username: account.username = username
        if first_name: account.first_name = first_name
        account.is_premium = is_premium
        account.is_active = set_active
        account.status = "ACTIVE"
        account.updated_at = datetime.datetime.utcnow()
    else:
        account = SenderAccount(
            phone=clean_phone, session_string=session_string,
            user_id=user_id, username=username, first_name=first_name,
            is_premium=is_premium, is_active=set_active, status="ACTIVE"
        )
        session.add(account)

    await session.commit()
    await session.refresh(account)
    return account

async def get_all_sender_accounts(session: AsyncSession) -> list[SenderAccount]:
    result = await session.execute(select(SenderAccount).order_by(SenderAccount.id.asc()))
    return list(result.scalars().all())

async def get_active_sender_account(session: AsyncSession) -> SenderAccount | None:
    result = await session.execute(select(SenderAccount).where(SenderAccount.is_active == True))
    acc = result.scalars().first()
    if not acc:
        result2 = await session.execute(select(SenderAccount).order_by(SenderAccount.id.asc()))
        acc = result2.scalars().first()
        if acc:
            acc.is_active = True
            await session.commit()
    return acc

async def set_active_sender_account(session: AsyncSession, account_id: int) -> SenderAccount | None:
    await session.execute(update(SenderAccount).values(is_active=False))
    result = await session.execute(select(SenderAccount).where(SenderAccount.id == account_id))
    acc = result.scalars().first()
    if acc:
        acc.is_active = True
        await session.commit()
        await session.refresh(acc)
    return acc

async def update_sender_account_status(session: AsyncSession, account_id: int, status: str):
    await session.execute(update(SenderAccount).where(SenderAccount.id == account_id).values(status=status))
    await session.commit()

async def delete_sender_account(session: AsyncSession, account_id: int) -> bool:
    await session.execute(delete(SenderAccount).where(SenderAccount.id == account_id))
    await session.commit()
    return True

# ==================== DAILY JOIN LIMIT TRACKING ====================

async def check_daily_join_limit(session: AsyncSession, account_id: int) -> dict:
    """Returns {'allowed': bool, 'used': int, 'limit': int, 'remaining': int}."""
    result = await session.execute(select(SenderAccount).where(SenderAccount.id == account_id))
    acc = result.scalars().first()
    if not acc:
        return {"allowed": False, "used": 0, "limit": config.MAX_JOINS_PER_DAY, "remaining": 0}

    now = datetime.datetime.utcnow()
    reset_date = acc.last_join_reset or now
    if (now - reset_date).total_seconds() > 86400:
        acc.joins_today = 0
        acc.last_join_reset = now
        await session.commit()

    used = acc.joins_today or 0
    remaining = max(0, config.MAX_JOINS_PER_DAY - used)
    return {"allowed": remaining > 0, "used": used, "limit": config.MAX_JOINS_PER_DAY, "remaining": remaining}

async def increment_daily_joins(session: AsyncSession, account_id: int):
    result = await session.execute(select(SenderAccount).where(SenderAccount.id == account_id))
    acc = result.scalars().first()
    if acc:
        acc.joins_today = (acc.joins_today or 0) + 1
        await session.commit()

# ==================== JOIN LOGS ====================

async def log_join_attempt(session: AsyncSession, account_id: int, identifier: str, status: str, error: str = None):
    log = JoinLog(account_id=account_id, identifier=identifier, status=status, error_reason=error)
    session.add(log)
    await session.commit()

async def get_join_report(session: AsyncSession, account_id: int) -> dict:
    """Aggregate join stats for an account."""
    result = await session.execute(
        select(JoinLog.status, func.count(JoinLog.id))
        .where(JoinLog.account_id == account_id)
        .group_by(JoinLog.status)
    )
    stats = {"JOINED": 0, "FAILED": 0, "ALREADY_MEMBER": 0, "FLOOD_WAIT": 0, "TOTAL": 0}
    for status, count in result.all():
        stats[status] = count
        stats["TOTAL"] += count
    return stats

async def get_join_logs(session: AsyncSession, account_id: int, limit: int = 50, status_filter: str = None):
    q = select(JoinLog).where(JoinLog.account_id == account_id)
    if status_filter:
        q = q.where(JoinLog.status == status_filter)
    q = q.order_by(JoinLog.joined_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())

# ==================== GROUP CRUD (PER-ACCOUNT) ====================

KNOWN_BAD_WORDS = {
    "comments", "twitter", "discord", "crypto", "telegram", "card", "dealer",
    "game", "sleep", "follows", "likes", "brend", "neon", "marketing", "tools",
    "accounts", "community", "artists", "cosmetics", "legit", "marketplace",
    "onlyfans", "jual", "beli", "market", "trusted", "referral", "link", "gain",
    "view", "views", "promo", "admin", "owner", "service", "services", "price",
    "channel", "group", "click", "here", "share", "order", "stock", "update",
    "contact", "bot", "store", "deals", "offer", "discount", "seller", "buyer"
}

def _is_valid_group_identifier(identifier: str) -> bool:
    if not identifier or not isinstance(identifier, str):
        return False
    raw = identifier.strip()
    clean_name = raw.lstrip("@").lower()
    if clean_name in KNOWN_BAD_WORDS:
        return False
    if re.match(r'https?://t\.me/(joinchat/|\+)[a-zA-Z0-9_\-]+$', raw):
        return True
    if re.match(r'https?://t\.me/[a-zA-Z][a-zA-Z0-9_]{3,31}$', raw):
        return True
    if re.match(r'^@[a-zA-Z][a-zA-Z0-9_]{3,31}$', raw):
        return True
    if re.match(r'^-100\d{7,13}$', raw) or re.match(r'^-\d{7,13}$', raw) or raw.lstrip("-").isdigit():
        return True
    return False

async def bulk_add_groups_for_account(session: AsyncSession, account_id: int, identifiers: list[str]) -> tuple[int, int]:
    """Import groups linked to a specific phone number account."""
    seen = set()
    clean_list = []
    for raw in identifiers:
        clean = raw.strip()
        if not clean:
            continue
        if not clean.startswith("http") and not clean.startswith("@") and not clean.startswith("-") and not clean.isdigit():
            clean = f"@{clean}"
        if not _is_valid_group_identifier(clean):
            continue
        if clean not in seen:
            seen.add(clean)
            clean_list.append(clean)

    if not clean_list:
        return 0, 0

    # Check existing for this account
    existing_result = await session.execute(
        select(Group.identifier).where(Group.account_id == account_id)
    )
    existing_set = set(existing_result.scalars().all())

    new_items = [c for c in clean_list if c not in existing_set]
    existing_count = len(clean_list) - len(new_items)

    if not new_items:
        return 0, existing_count

    for ident in new_items:
        g = Group(account_id=account_id, identifier=ident, title=ident, is_joined=False, is_selected=True, status="ACTIVE")
        session.add(g)
    await session.commit()
    return len(new_items), existing_count

async def get_groups_for_account(session: AsyncSession, account_id: int) -> list[Group]:
    result = await session.execute(
        select(Group).where(Group.account_id == account_id).order_by(Group.id.asc())
    )
    return list(result.scalars().all())

async def get_unjoined_groups_for_account(session: AsyncSession, account_id: int) -> list[Group]:
    result = await session.execute(
        select(Group).where(
            Group.account_id == account_id,
            Group.is_joined == False,
            Group.status.in_(["ACTIVE", "SLOWMODE"])
        ).order_by(Group.id.asc())
    )
    return list(result.scalars().all())

async def get_active_groups_for_account(session: AsyncSession, account_id: int) -> list[Group]:
    result = await session.execute(
        select(Group).where(
            Group.account_id == account_id,
            Group.status.in_(["ACTIVE", "SLOWMODE"])
        ).order_by(Group.last_sent_at.asc().nullsfirst(), Group.id.asc())
    )
    return list(result.scalars().all())

async def get_selected_groups(session: AsyncSession, account_id: int) -> list[Group]:
    result = await session.execute(
        select(Group).where(
            Group.account_id == account_id,
            Group.is_selected == True,
            Group.status.in_(["ACTIVE", "SLOWMODE"])
        ).order_by(Group.id.asc())
    )
    return list(result.scalars().all())

async def get_group_stats_for_account(session: AsyncSession, account_id: int) -> dict:
    result = await session.execute(
        select(Group.status, func.count(Group.id))
        .where(Group.account_id == account_id)
        .group_by(Group.status)
    )
    stats = {"TOTAL": 0, "ACTIVE": 0, "SLOWMODE": 0, "BANNED": 0, "RESTRICTED": 0, "INVALID_LINK": 0}
    for status, count in result.all():
        stats[status] = count
        stats["TOTAL"] += count
    return stats

async def toggle_group_selection(session: AsyncSession, group_id: int) -> bool:
    result = await session.execute(select(Group).where(Group.id == group_id))
    g = result.scalars().first()
    if g:
        g.is_selected = not g.is_selected
        await session.commit()
        return g.is_selected
    return False

async def select_all_groups(session: AsyncSession, account_id: int):
    await session.execute(
        update(Group).where(Group.account_id == account_id).values(is_selected=True)
    )
    await session.commit()

async def deselect_all_groups(session: AsyncSession, account_id: int):
    await session.execute(
        update(Group).where(Group.account_id == account_id).values(is_selected=False)
    )
    await session.commit()

async def sync_telegram_groups(session: AsyncSession, account_id: int, telegram_groups: list[dict]) -> dict:
    """Sync real Telegram groups into DB using raw INSERT OR IGNORE.

    WHY raw SQL: SQLAlchemy session.flush() inside try/except corrupts the session
    after the first constraint error — all subsequent inserts silently fail with
    'Can't execute query: transaction has been rolled back'. Using raw SQL INSERT OR IGNORE
    handles conflicts at the database level without ever touching the session state.
    """
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Load existing groups for this account
    existing_result = await session.execute(
        select(Group).where(Group.account_id == account_id)
    )
    existing_groups = list(existing_result.scalars().all())
    existing_chat_ids = {g.chat_id for g in existing_groups if g.chat_id is not None}
    existing_idents   = {g.identifier.lower() for g in existing_groups if g.identifier}

    added = 0
    for tg in telegram_groups:
        cid   = tg["chat_id"]
        uname = tg.get("username")
        ident = f"@{uname}" if uname else str(cid)
        title = (tg.get("title") or ident)[:255]
        ident = ident[:255]

        # Already in DB for this account → just update title/status
        if cid in existing_chat_ids or (ident and ident.lower() in existing_idents):
            matching = next(
                (g for g in existing_groups
                 if (g.chat_id is not None and g.chat_id == cid)
                 or (g.identifier and g.identifier.lower() == ident.lower())),
                None
            )
            if matching:
                if not matching.chat_id:
                    matching.chat_id = cid
                if title:
                    matching.title = title
                matching.is_joined = True
                matching.status    = "ACTIVE"
            continue

        # New group for this account
        try:
            await session.execute(text("""
                INSERT INTO target_groups
                    (account_id, chat_id, title, identifier,
                     is_joined, is_selected, status,
                     failure_count, consecutive_failures, slowmode_seconds,
                     created_at, updated_at)
                VALUES
                    (:acc, :cid, :title, :ident,
                     1, 1, 'ACTIVE',
                     0, 0, 0,
                     :now, :now)
            """), {"acc": account_id, "cid": cid,
                   "title": title, "ident": ident, "now": now_str})
            added += 1
            existing_chat_ids.add(cid)
            existing_idents.add(ident.lower())
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"sync_telegram_groups: insert failed for group {ident} on account #{account_id}: {e}"
            )
            continue

    await session.commit()

    total_result = await session.execute(
        select(func.count(Group.id)).where(Group.account_id == account_id)
    )
    total = total_result.scalar() or 0
    return {"added": added, "existing": len(existing_groups), "total": total}

async def update_group_status(
    session: AsyncSession, group_id: int, status: str,
    error: str = None, is_success: bool = False, slowmode_sec: int = 0
):
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalars().first()
    if not group:
        return
    group.status = status
    group.last_error = error
    group.updated_at = datetime.datetime.utcnow()
    if is_success:
        group.last_sent_at = datetime.datetime.utcnow()
        group.consecutive_failures = 0
        group.failure_count = max(0, (group.failure_count or 0))
    else:
        group.failure_count = (group.failure_count or 0) + 1
        group.consecutive_failures = (group.consecutive_failures or 0) + 1
    if slowmode_sec:
        group.slowmode_seconds = slowmode_sec
    await session.commit()

async def delete_group(session: AsyncSession, group_id: int):
    await session.execute(delete(Group).where(Group.id == group_id))
    await session.commit()

async def smart_clean_groups_for_account(session: AsyncSession, account_id: int) -> dict:
    """Purges dead/invalid groups for a specific account."""
    result = await session.execute(select(Group).where(Group.account_id == account_id))
    groups = result.scalars().all()
    deleted = 0
    for g in groups:
        clean_name = g.identifier.strip().lstrip("@").lower()
        is_bad = g.status in ["INVALID_LINK", "BANNED"]
        is_invalid = not _is_valid_group_identifier(g.identifier)
        is_known_bad = clean_name in KNOWN_BAD_WORDS
        is_cast_err = g.last_error and "Cannot cast InputPeerUser" in g.last_error
        is_not_found = g.last_error and ("No user has" in g.last_error or "Nobody is using" in g.last_error)
        if is_bad or is_invalid or is_known_bad or is_cast_err or is_not_found:
            await session.delete(g)
            deleted += 1
    if deleted:
        await session.commit()
    active = await session.execute(
        select(func.count(Group.id)).where(Group.account_id == account_id, Group.status == "ACTIVE")
    )
    return {"deleted": deleted, "active": active.scalar() or 0}

async def get_groups_paginated(session: AsyncSession, account_id: int, page: int = 1, per_page: int = 10) -> tuple[list[Group], int]:
    """Returns (groups_on_page, total_pages) for paginated group selection UI."""
    total_result = await session.execute(
        select(func.count(Group.id)).where(
            Group.account_id == account_id,
            Group.status.in_(["ACTIVE", "SLOWMODE"])
        )
    )
    total = total_result.scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page
    result = await session.execute(
        select(Group).where(
            Group.account_id == account_id,
            Group.status.in_(["ACTIVE", "SLOWMODE"])
        ).order_by(Group.id.asc()).limit(per_page).offset(offset)
    )
    return list(result.scalars().all()), total_pages

# ==================== PROMO MESSAGE (PER-ACCOUNT) ====================

async def get_or_create_account_promo(session: AsyncSession, account_id: int, phone: str = None) -> PromoMessage:
    result = await session.execute(select(PromoMessage).where(PromoMessage.account_id == account_id))
    promo = result.scalars().first()
    if not promo:
        import datetime
        title = f"Campaign ({phone})" if phone else f"Campaign (Account #{account_id})"
        promo = PromoMessage(
            account_id=account_id, title=title,
            text="Your promotional message here. Edit this in ✏️ Message Setup.",
            media_type="none", interval_hours=2.0,
            is_enabled=False,                              # OFF by default — user must enable in ⏰ Scheduler
            last_run_at=datetime.datetime.utcnow()         # Start timer from now so it doesn't fire instantly
        )
        session.add(promo)
        await session.commit()
        await session.refresh(promo)
    return promo

async def update_account_promo(session: AsyncSession, account_id: int, text: str,
                               media_type: str = "none", media_file_id: str = None,
                               media_path: str = None, phone: str = None,
                               saved_msg_id: int = None):
    promo = await get_or_create_account_promo(session, account_id, phone)
    promo.text = text
    promo.media_type = media_type
    promo.media_file_id = media_file_id
    promo.media_path = media_path
    if saved_msg_id is not None:
        promo.saved_msg_id = saved_msg_id
    promo.updated_at = datetime.datetime.utcnow()
    await session.commit()

async def set_account_interval(session: AsyncSession, account_id: int, interval_hours: float):
    promo = await get_or_create_account_promo(session, account_id)
    promo.interval_hours = interval_hours
    await session.commit()

async def set_account_campaign_enabled(session: AsyncSession, account_id: int, enabled: bool):
    promo = await get_or_create_account_promo(session, account_id)
    promo.is_enabled = enabled
    await session.commit()

# ==================== BROADCAST CYCLES & LOGS ====================

async def create_cycle(session: AsyncSession, total_targets: int, account_id: int = None, account_phone: str = None) -> BroadcastCycle:
    cycle = BroadcastCycle(
        account_id=account_id, account_phone=account_phone,
        total_targets=total_targets, status="RUNNING"
    )
    session.add(cycle)
    await session.commit()
    await session.refresh(cycle)
    return cycle

async def finish_cycle(session: AsyncSession, cycle_id: int, status: str,
                       success: int, failed: int, skipped: int, duration: int):
    result = await session.execute(select(BroadcastCycle).where(BroadcastCycle.id == cycle_id))
    cycle = result.scalars().first()
    if cycle:
        cycle.status = status
        cycle.success_count = success
        cycle.failed_count = failed
        cycle.skipped_count = skipped
        cycle.duration_seconds = duration
        cycle.completed_at = datetime.datetime.utcnow()
        await session.commit()

async def log_broadcast_result(session: AsyncSession, cycle_id: int, group_id: int,
                               group_identifier: str, status: str, error_reason: str = None):
    log = BroadcastLog(
        cycle_id=cycle_id, group_id=group_id,
        group_identifier=group_identifier, status=status, error_reason=error_reason
    )
    session.add(log)
    await session.commit()

async def get_recent_cycles(session: AsyncSession, limit: int = 5, account_id: int = None):
    q = select(BroadcastCycle)
    if account_id:
        q = q.where(BroadcastCycle.account_id == account_id)
    q = q.order_by(BroadcastCycle.started_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())

async def get_cycle_by_id(session: AsyncSession, cycle_id: int) -> BroadcastCycle | None:
    result = await session.execute(select(BroadcastCycle).where(BroadcastCycle.id == cycle_id))
    return result.scalars().first()

async def get_cycle_failed_logs(session: AsyncSession, cycle_id: int):
    result = await session.execute(
        select(BroadcastLog).where(
            BroadcastLog.cycle_id == cycle_id, BroadcastLog.status == "FAILED"
        ).order_by(BroadcastLog.sent_at.asc())
    )
    return list(result.scalars().all())

async def get_cycle_sent_logs(session: AsyncSession, cycle_id: int):
    result = await session.execute(
        select(BroadcastLog).where(
            BroadcastLog.cycle_id == cycle_id, BroadcastLog.status == "SENT"
        ).order_by(BroadcastLog.sent_at.asc())
    )
    return list(result.scalars().all())

# ==================== BOT SETTINGS ====================

async def get_setting(session: AsyncSession, key: str, default: str = None) -> str:
    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    s = result.scalars().first()
    return s.value if s else default

async def set_setting(session: AsyncSession, key: str, value: str, description: str = None):
    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    s = result.scalars().first()
    if s:
        s.value = value
        if description:
            s.description = description
    else:
        s = BotSetting(key=key, value=value, description=description)
        session.add(s)
    await session.commit()

async def seed_default_settings(session: AsyncSession):
    defaults = {
        "broadcast_enabled": ("true", "Master broadcast toggle"),
        "interval_hours": (str(config.DEFAULT_INTERVAL_HOURS), "Global broadcast interval"),
        "min_delay_sec": (str(config.MIN_DELAY_PER_GROUP), "Min delay between messages"),
        "max_delay_sec": (str(config.MAX_DELAY_PER_GROUP), "Max delay between messages"),
        "batch_size": (str(config.BATCH_SIZE), "Messages per batch"),
        "batch_cooldown_sec": (str(config.BATCH_COOLDOWN), "Cooldown between batches"),
        "spintax_enabled": ("true", "Spintax text rotation"),
        "anti_hash_enabled": ("true", "Zero-width anti-hash jitter"),
    }
    for key, (value, desc) in defaults.items():
        existing = await get_setting(session, key)
        if existing is None:
            await set_setting(session, key, value, desc)
