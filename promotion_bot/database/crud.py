import datetime
from sqlalchemy import select, update, delete, func, desc
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

async def bulk_add_groups(session: AsyncSession, identifiers: list[str]) -> tuple[int, int]:
    added = 0
    existing = 0
    for raw in identifiers:
        clean = raw.strip()
        if not clean:
            continue
        if not clean.startswith("http") and not clean.startswith("@") and not clean.startswith("-100") and not clean.lstrip("-").isdigit():
            clean = f"@{clean}"
        
        result = await session.execute(select(Group).where(Group.identifier == clean))
        if result.scalars().first():
            existing += 1
        else:
            grp = Group(identifier=clean, title=clean, status="ACTIVE")
            session.add(grp)
            added += 1
    await session.commit()
    return added, existing

async def get_active_groups(session: AsyncSession) -> list[Group]:
    result = await session.execute(
        select(Group).where(Group.status.in_(["ACTIVE", "SLOWMODE"])).order_by(Group.id.asc())
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

async def reset_all_group_statuses(session: AsyncSession) -> int:
    stmt = update(Group).values(status="ACTIVE", consecutive_failures=0, last_error=None)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount

# ==================== PROMO MESSAGE CRUD ====================

async def get_active_promo_message(session: AsyncSession) -> PromoMessage:
    result = await session.execute(
        select(PromoMessage).where(PromoMessage.is_active == True).order_by(PromoMessage.id.desc())
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
        promo = PromoMessage(title="Default Promo", text=default_text, media_type="none", is_active=True)
        session.add(promo)
        await session.commit()
        await session.refresh(promo)
    return promo

async def update_promo_message(
    session: AsyncSession,
    text: str,
    media_type: str = "none",
    media_file_id: str = None,
    media_path: str = None
) -> PromoMessage:
    result = await session.execute(select(PromoMessage).where(PromoMessage.is_active == True))
    promo = result.scalars().first()
    if promo:
        promo.text = text
        promo.media_type = media_type
        promo.media_file_id = media_file_id
        promo.media_path = media_path
        promo.updated_at = datetime.datetime.utcnow()
    else:
        promo = PromoMessage(
            text=text,
            media_type=media_type,
            media_file_id=media_file_id,
            media_path=media_path,
            is_active=True
        )
        session.add(promo)
    await session.commit()
    await session.refresh(promo)
    return promo

# ==================== BROADCAST CYCLE & LOG CRUD ====================

async def create_cycle(session: AsyncSession, total_targets: int) -> BroadcastCycle:
    cycle = BroadcastCycle(
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
