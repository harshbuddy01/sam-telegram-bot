import datetime
from sqlalchemy import select, update, delete, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Group, PromoMessage, BroadcastCycle, BroadcastLog, BotSetting, SenderAccount
import config

# ==================== SENDER ACCOUNTS (MULTI-NUMBER) ====================

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
        # Deactivate all other accounts
        await session.execute(update(SenderAccount).values(is_active=False))
        
    if account:
        account.session_string = session_string
        account.user_id = user_id
        account.username = username
        account.first_name = first_name
        account.is_premium = is_premium
        account.is_active = set_active
        account.status = "ACTIVE"
        account.updated_at = datetime.datetime.utcnow()
    else:
        account = SenderAccount(
            phone=clean_phone,
            session_string=session_string,
            user_id=user_id,
            username=username,
            first_name=first_name,
            is_premium=is_premium,
            is_active=set_active,
            status="ACTIVE"
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
        # Fallback to the first account if none marked active
        result2 = await session.execute(select(SenderAccount).order_by(SenderAccount.id.asc()))
        acc = result2.scalars().first()
        if acc:
            acc.is_active = True
            await session.commit()
    return acc

async def set_active_sender_account(session: AsyncSession, account_id: int) -> SenderAccount | None:
    # Deactivate all
    await session.execute(update(SenderAccount).values(is_active=False))
    # Activate target
    result = await session.execute(select(SenderAccount).where(SenderAccount.id == account_id))
    acc = result.scalars().first()
    if acc:
        acc.is_active = True
        await session.commit()
        await session.refresh(acc)
    return acc

async def delete_sender_account(session: AsyncSession, account_id: int) -> bool:
    stmt = delete(SenderAccount).where(SenderAccount.id == account_id)
    await session.execute(stmt)
    await session.commit()
    return True

# ==================== GROUP CRUD ====================

async def add_or_get_group(session: AsyncSession, identifier: str, title: str = None, chat_id: int = None) -> tuple[Group, bool]:
    clean_id = identifier.strip()
    result = await session.execute(select(Group).where(Group.identifier == clean_id))
    group = result.scalars().first()
    if group:
        if title: group.title = title
        if chat_id: group.chat_id = chat_id
        await session.commit()
        return group, False
    
    group = Group(
        identifier=clean_id,
        title=title or clean_id,
        chat_id=chat_id,
        status="ACTIVE"
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group, True

def _is_valid_group_identifier(raw: str) -> bool:
    """
    Returns True only for valid group identifiers:
    - t.me/username or t.me/+hash (invite links)
    - @username (4–32 alphanumeric chars + underscore, ASCII only)
    - Negative chat IDs like -1001234567890
    """
    import re
    # Valid invite link
    if re.match(r'https?://t\.me/(\+|joinchat/)[a-zA-Z0-9_-]{4,}', raw):
        return True
    # Valid t.me/username
    if re.match(r'https?://t\.me/[a-zA-Z][a-zA-Z0-9_]{3,31}$', raw):
        return True
    # Valid @username (ASCII letters/digits/underscore, 4-32 chars)
    if re.match(r'^@[a-zA-Z][a-zA-Z0-9_]{3,31}$', raw):
        return True
    # Valid numeric chat ID (starts with -100)
    if re.match(r'^-100\d{7,13}$', raw):
        return True
    return False

async def bulk_add_groups(session: AsyncSession, identifiers: list[str]) -> tuple[int, int]:
    now = datetime.datetime.utcnow().isoformat()

    # Step 1: Clean, normalize, validate and deduplicate ALL identifiers in Python
    seen_in_batch = set()
    clean_list = []
    for raw in identifiers:
        clean = raw.strip()
        if not clean:
            continue
        # Normalize: add @ prefix if no prefix
        if not clean.startswith("http") and not clean.startswith("@") and not clean.startswith("-100") and not clean.lstrip("-").isdigit():
            clean = f"@{clean}"
        # Strict validation — skip garbage entries like @-, @گروه, @and, etc.
        if not _is_valid_group_identifier(clean):
            continue
        if clean not in seen_in_batch:
            seen_in_batch.add(clean)
            clean_list.append(clean)

    if not clean_list:
        return 0, 0

    # Step 2: Fetch existing identifiers in ONE bulk query
    existing_result = await session.execute(select(Group.identifier))
    existing_db_set = set(existing_result.scalars().all())

    # Step 3: Split into new vs existing
    new_items = [c for c in clean_list if c not in existing_db_set]
    existing_count = len(clean_list) - len(new_items)

    if not new_items:
        return 0, existing_count

    # Step 4: INSERT OR IGNORE using raw SQL (bypasses ORM autoflush entirely)
    # 100% safe — even if somehow a duplicate sneaks through, SQLite silently ignores it
    await session.execute(
        text(
            "INSERT OR IGNORE INTO target_groups "
            "(identifier, title, is_joined, status, failure_count, consecutive_failures, slowmode_seconds, created_at, updated_at) "
            "VALUES (:identifier, :title, 0, 'ACTIVE', 0, 0, 0, :now, :now)"
        ),
        [{"identifier": c, "title": c, "now": now} for c in new_items]
    )
    await session.commit()

    return len(new_items), existing_count


async def get_unjoined_groups(session: AsyncSession) -> list[Group]:
    result = await session.execute(
        select(Group).where(
            Group.is_joined == False,
            Group.status.in_(["ACTIVE", "SLOWMODE"])
        ).order_by(Group.id.asc())
    )
    return list(result.scalars().all())

async def get_active_groups(session: AsyncSession) -> list[Group]:
    result = await session.execute(
        select(Group).where(Group.status.in_(["ACTIVE", "SLOWMODE"])).order_by(Group.last_sent_at.asc().nullsfirst(), Group.id.asc())
    )
    return list(result.scalars().all())

async def get_all_groups(session: AsyncSession) -> list[Group]:
    result = await session.execute(select(Group).order_by(Group.id.asc()))
    return list(result.scalars().all())

async def get_groups_by_status(session: AsyncSession, status: str) -> list[Group]:
    result = await session.execute(select(Group).where(Group.status == status).order_by(Group.id.asc()))
    return list(result.scalars().all())

async def get_group_stats(session: AsyncSession) -> dict:
    result = await session.execute(
        select(Group.status, func.count(Group.id)).group_by(Group.status)
    )
    stats = {"TOTAL": 0, "ACTIVE": 0, "SLOWMODE": 0, "BANNED": 0, "RESTRICTED": 0, "INVALID_LINK": 0, "MUTED": 0}
    total = 0
    for status, count in result.all():
        stats[status] = count
        total += count
    stats["TOTAL"] = total
    return stats

async def update_group_status(
    session: AsyncSession, 
    group_id: int, 
    status: str, 
    error: str = None, 
    is_success: bool = False,
    slowmode_sec: int = 0
):
    stmt = select(Group).where(Group.id == group_id)
    result = await session.execute(stmt)
    group = result.scalars().first()
    if not group:
        return
    
    group.status = status
    group.last_error = error
    group.updated_at = datetime.datetime.utcnow()
    
    if is_success:
        group.last_sent_at = datetime.datetime.utcnow()
        group.consecutive_failures = 0
        group.slowmode_seconds = 0
    else:
        group.failure_count += 1
        group.consecutive_failures += 1
        if slowmode_sec > 0:
            group.slowmode_seconds = slowmode_sec
            
    await session.commit()

async def delete_group(session: AsyncSession, group_id: int) -> bool:
    stmt = delete(Group).where(Group.id == group_id)
    await session.execute(stmt)
    await session.commit()
    return True

async def delete_all_groups_by_status(session: AsyncSession, status: str) -> int:
    stmt = delete(Group).where(Group.status == status)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount

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
    
    # Exclude common single dictionary words
    clean_name = raw.lstrip("@").lower()
    if clean_name in KNOWN_BAD_WORDS:
        return False

    # Valid t.me/joinchat/... or t.me/+hash
    if re.match(r'https?://t\.me/(joinchat/|\+)[a-zA-Z0-9_\-]+$', raw):
        return True
    # Valid t.me/username (at least 4 chars)
    if re.match(r'https?://t\.me/[a-zA-Z][a-zA-Z0-9_]{3,31}$', raw):
        return True
    # Valid @username (at least 4 chars)
    if re.match(r'^@[a-zA-Z][a-zA-Z0-9_]{3,31}$', raw):
        return True
    # Valid numeric chat ID (starts with -100)
    if re.match(r'^-100\d{7,13}$', raw):
        return True
    return False

async def purge_invalid_identifiers(session: AsyncSession) -> int:
    result = await session.execute(select(Group))
    groups = result.scalars().all()
    deleted_count = 0
    for g in groups:
        clean_name = g.identifier.strip().lstrip("@").lower()
        if not _is_valid_group_identifier(g.identifier) or clean_name in KNOWN_BAD_WORDS:
            await session.delete(g)
            deleted_count += 1
    if deleted_count > 0:
        await session.commit()
    return deleted_count

async def smart_clean_and_purge_groups(session: AsyncSession) -> dict:
    """Purges all dead/invalid/banned/user-profile groups and resets active groups."""
    result = await session.execute(select(Group))
    groups = result.scalars().all()
    deleted_count = 0
    for g in groups:
        clean_name = g.identifier.strip().lstrip("@").lower()
        is_bad_status = g.status in ["INVALID_LINK", "BANNED"]
        is_invalid_syntax = not _is_valid_group_identifier(g.identifier)
        is_known_bad = clean_name in KNOWN_BAD_WORDS
        is_user_cast_error = g.last_error and "Cannot cast InputPeerUser" in g.last_error
        is_not_found = g.last_error and ("No user has" in g.last_error or "Nobody is using this username" in g.last_error)

        if is_bad_status or is_invalid_syntax or is_known_bad or is_user_cast_error or is_not_found:
            await session.delete(g)
            deleted_count += 1
        elif g.status in ["RESTRICTED", "SLOWMODE"]:
            g.status = "ACTIVE"
            g.consecutive_failures = 0
            g.last_error = None

    if deleted_count > 0:
        await session.commit()

    active_count = len(await get_active_groups(session))
    return {"deleted": deleted_count, "active": active_count}

async def reset_all_group_statuses(session: AsyncSession) -> int:
    stmt = update(Group).values(status="ACTIVE", consecutive_failures=0, last_error=None)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount

# ==================== PROMO MESSAGE & MULTI-ACCOUNT CAMPAIGNS ====================

async def get_active_promo_message(session: AsyncSession) -> PromoMessage:
    result = await session.execute(
        select(PromoMessage).where(PromoMessage.account_id == None, PromoMessage.is_active == True).order_by(PromoMessage.id.desc())
    )
    promo = result.scalars().first()
    if not promo:
        default_text = (
            "🔥 <b>PREMIUM SERVICES & ACCOUNTS AVAILABLE!</b> 🔥\n\n"
            "✨ High Quality • Instant Delivery • 24/7 Support\n"
            "💎 Netflix, Prime Video, Claude Pro, ChatGPT & more!\n\n"
            "👉 <b>Order Now:</b> @SamStoreAd_Bot\n"
            "🌐 <b>Official Channel:</b> @SamStoreServices"
        )
        promo = PromoMessage(title="Default Promo Template", text=default_text, media_type="none", is_active=True)
        session.add(promo)
        await session.commit()
        await session.refresh(promo)
    return promo

async def get_or_create_account_promo(session: AsyncSession, account_id: int, phone: str = None) -> PromoMessage:
    result = await session.execute(
        select(PromoMessage).where(PromoMessage.account_id == account_id)
    )
    promo = result.scalars().first()
    if not promo:
        global_promo = await get_active_promo_message(session)
        title = f"Campaign ({phone or f'Account #{account_id}'})"
        promo = PromoMessage(
            account_id=account_id,
            title=title,
            text=global_promo.text,
            media_type=global_promo.media_type,
            media_file_id=global_promo.media_file_id,
            media_path=global_promo.media_path,
            interval_hours=2.0,
            is_enabled=True,
            status="IDLE",
            is_active=True
        )
        session.add(promo)
        await session.commit()
        await session.refresh(promo)
    return promo

async def update_account_promo(
    session: AsyncSession,
    account_id: int,
    text: str,
    media_type: str = "none",
    media_file_id: str = None,
    media_path: str = None,
    phone: str = None
) -> PromoMessage:
    promo = await get_or_create_account_promo(session, account_id, phone)
    promo.text = text
    promo.media_type = media_type
    promo.media_file_id = media_file_id
    promo.media_path = media_path
    promo.updated_at = datetime.datetime.utcnow()
    await session.commit()
    await session.refresh(promo)
    return promo

async def set_account_interval(session: AsyncSession, account_id: int, interval_hours: float):
    promo = await get_or_create_account_promo(session, account_id)
    promo.interval_hours = float(interval_hours)
    promo.updated_at = datetime.datetime.utcnow()
    await session.commit()

async def set_account_campaign_status(session: AsyncSession, account_id: int, status: str):
    promo = await get_or_create_account_promo(session, account_id)
    promo.status = status
    promo.updated_at = datetime.datetime.utcnow()
    await session.commit()

async def get_all_account_campaigns(session: AsyncSession) -> list[tuple[SenderAccount, PromoMessage]]:
    accounts = await get_all_sender_accounts(session)
    pairs = []
    for acc in accounts:
        promo = await get_or_create_account_promo(session, acc.id, acc.phone)
        pairs.append((acc, promo))
    return pairs

async def update_promo_message(
    session: AsyncSession,
    text: str,
    media_type: str = "none",
    media_file_id: str = None,
    media_path: str = None
) -> PromoMessage:
    promo = await get_active_promo_message(session)
    promo.text = text
    promo.media_type = media_type
    promo.media_file_id = media_file_id
    promo.media_path = media_path
    promo.updated_at = datetime.datetime.utcnow()
    await session.commit()
    await session.refresh(promo)
    return promo

# ==================== BROADCAST CYCLE & LOG CRUD ====================

async def create_cycle(session: AsyncSession, total_targets: int, account_id: int = None, account_phone: str = None) -> BroadcastCycle:
    cycle = BroadcastCycle(
        account_id=account_id,
        account_phone=account_phone,
        started_at=datetime.datetime.utcnow(),
        status="RUNNING",
        total_targets=total_targets,
        success_count=0,
        failed_count=0,
        skipped_count=0
    )
    session.add(cycle)
    await session.commit()
    await session.refresh(cycle)
    return cycle

async def finish_cycle(
    session: AsyncSession,
    cycle_id: int,
    status: str,
    success: int,
    failed: int,
    skipped: int,
    duration: int
):
    stmt = select(BroadcastCycle).where(BroadcastCycle.id == cycle_id)
    result = await session.execute(stmt)
    cycle = result.scalars().first()
    if cycle:
        cycle.completed_at = datetime.datetime.utcnow()
        cycle.status = status
        cycle.success_count = success
        cycle.failed_count = failed
        cycle.skipped_count = skipped
        cycle.duration_seconds = duration
        await session.commit()

async def log_broadcast_result(
    session: AsyncSession,
    cycle_id: int,
    group_id: int,
    group_identifier: str,
    status: str,
    error_reason: str = None
):
    log = BroadcastLog(
        cycle_id=cycle_id,
        group_id=group_id,
        group_identifier=group_identifier,
        status=status,
        error_reason=error_reason,
        sent_at=datetime.datetime.utcnow()
    )
    session.add(log)
    await session.commit()

async def get_recent_cycles(session: AsyncSession, limit: int = 5) -> list[BroadcastCycle]:
    result = await session.execute(
        select(BroadcastCycle).order_by(desc(BroadcastCycle.id)).limit(limit)
    )
    return list(result.scalars().all())

async def get_cycle_by_id(session: AsyncSession, cycle_id: int) -> BroadcastCycle | None:
    result = await session.execute(select(BroadcastCycle).where(BroadcastCycle.id == cycle_id))
    return result.scalars().first()

async def get_cycle_sent_logs(session: AsyncSession, cycle_id: int) -> list[BroadcastLog]:
    result = await session.execute(
        select(BroadcastLog).where(
            BroadcastLog.cycle_id == cycle_id,
            BroadcastLog.status == "SENT"
        ).order_by(BroadcastLog.id.asc())
    )
    return list(result.scalars().all())

async def get_cycle_failed_logs(session: AsyncSession, cycle_id: int) -> list[BroadcastLog]:
    result = await session.execute(
        select(BroadcastLog).where(
            BroadcastLog.cycle_id == cycle_id,
            BroadcastLog.status.in_(["FAILED", "SLOWMODE", "SKIPPED"])
        ).order_by(BroadcastLog.id.asc())
    )
    return list(result.scalars().all())

# ==================== SETTINGS CRUD ====================

async def get_setting(session: AsyncSession, key: str, default: str = None) -> str:
    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    setting = result.scalars().first()
    return setting.value if setting else default

async def set_setting(session: AsyncSession, key: str, value: str, description: str = None):
    result = await session.execute(select(BotSetting).where(BotSetting.key == key))
    setting = result.scalars().first()
    if setting:
        setting.value = str(value)
        if description: setting.description = description
    else:
        setting = BotSetting(key=key, value=str(value), description=description)
        session.add(setting)
    await session.commit()

async def seed_default_settings(session: AsyncSession):
    defaults = {
        "broadcast_enabled": "true",
        "interval_hours": str(config.DEFAULT_INTERVAL_HOURS),
        "min_delay_sec": str(config.MIN_DELAY_PER_GROUP),
        "max_delay_sec": str(config.MAX_DELAY_PER_GROUP),
        "batch_size": str(config.BATCH_SIZE),
        "batch_cooldown_sec": str(config.BATCH_COOLDOWN),
        "spintax_enabled": "true"
    }
    for k, v in defaults.items():
        res = await session.execute(select(BotSetting).where(BotSetting.key == k))
        if not res.scalars().first():
            session.add(BotSetting(key=k, value=v))
    await session.commit()
