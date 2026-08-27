from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    get_or_create_account_promo,
    set_account_interval,
    set_account_campaign_enabled,
    get_setting,
    set_setting
)
from core.scheduler import scheduler
import config

router = Router()


@router.callback_query(F.data == "sec_scheduler")
async def cb_scheduler_menu(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass
    if state:
        await state.clear()

    async with AsyncSessionLocal() as session:
        is_enabled = await get_setting(session, "broadcast_enabled", "true")
        min_delay = await get_setting(session, "min_delay_sec", str(config.MIN_DELAY_PER_GROUP))
        max_delay = await get_setting(session, "max_delay_sec", str(config.MAX_DELAY_PER_GROUP))
        spintax = await get_setting(session, "spintax_enabled", "true")
        accounts = await get_all_sender_accounts(session)
        promos_map = {}
        for acc in accounts:
            p = await get_or_create_account_promo(session, acc.id, acc.phone)
            promos_map[acc.id] = p

    global_status = "🟢 ENABLED (Auto-Repeating)" if is_enabled.lower() == "true" else "🔴 PAUSED (Manual Only)"
    spintax_status = "🟢 ACTIVE" if spintax.lower() == "true" else "⚪ DISABLED"

    text = (
        "⏰ <b>BROADCAST SCHEDULER & TIMERS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚙️ <b>Global Auto-Repeat:</b> <b>{global_status}</b>\n"
        f"🛡️ <b>Anti-Ban Delays:</b> <code>{min_delay}s–{max_delay}s</code> per message\n"
        f"📝 <b>Spintax & Anti-Hash:</b> <b>{spintax_status}</b>\n\n"
        f"📱 <b>Per-Number Repeat Intervals:</b>\n"
    )

    if not accounts:
        text += "<i>No phone numbers connected.</i>\n"
    else:
        for acc in accounts:
            p = promos_map[acc.id]
            enabled_badge = "🟢 ON" if p.is_enabled else "⚪ OFF"
            user_lbl = f"@{acc.username}" if acc.username else (acc.first_name or "")
            text += (
                f"• <b>{acc.phone}</b> ({user_lbl})\n"
                f"   └ ⏱️ Interval: <b>Every {p.interval_hours} hours</b> | State: <b>{enabled_badge}</b>\n"
            )

    kb = []
    for acc in accounts:
        p = promos_map[acc.id]
        kb.append([
            InlineKeyboardButton(
                text=f"⏱️ Change Interval: {acc.phone} ({p.interval_hours}h)",
                callback_data=f"sched_acc_{acc.id}"
            )
        ])

    toggle_txt = "⏸️ Pause Auto-Repeat" if is_enabled.lower() == "true" else "▶️ Enable Auto-Repeat"
    kb.append([
        InlineKeyboardButton(text=toggle_txt, callback_data="sched_toggle_global"),
        InlineKeyboardButton(text="🔄 Toggle Spintax", callback_data="sched_toggle_spintax")
    ])
    kb.append([
        InlineKeyboardButton(text="⚡ Balanced Preset", callback_data="sched_preset_balanced"),
        InlineKeyboardButton(text="🛡️ Safe Preset", callback_data="sched_preset_safe")
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])

    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("sched_acc_"))
async def cb_edit_account_interval(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        acc = next((a for a in accounts if a.id == account_id), None)
        if not acc:
            return
        promo = await get_or_create_account_promo(session, account_id, acc.phone)

    user_lbl = f"@{acc.username}" if acc.username else (acc.first_name or "")
    text = (
        f"⏱️ <b>SET INTERVAL — {acc.phone}</b> ({user_lbl})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Current Repeat Interval: <b>Every {promo.interval_hours} Hours</b>\n"
        f"Auto-Broadcast Enabled: <b>{'🟢 YES' if promo.is_enabled else '⚪ NO'}</b>\n\n"
        "Select how frequently the bot should automatically broadcast to all selected groups:"
    )

    kb = [
        [
            InlineKeyboardButton(text="30 Min", callback_data=f"sched_set_{account_id}_0.5"),
            InlineKeyboardButton(text="1 Hour", callback_data=f"sched_set_{account_id}_1.0"),
            InlineKeyboardButton(text="2 Hours", callback_data=f"sched_set_{account_id}_2.0")
        ],
        [
            InlineKeyboardButton(text="4 Hours", callback_data=f"sched_set_{account_id}_4.0"),
            InlineKeyboardButton(text="6 Hours", callback_data=f"sched_set_{account_id}_6.0"),
            InlineKeyboardButton(text="12 Hours", callback_data=f"sched_set_{account_id}_12.0")
        ],
        [
            InlineKeyboardButton(
                text="🔴 Disable for this Number" if promo.is_enabled else "🟢 Enable for this Number",
                callback_data=f"sched_tog_acc_{account_id}"
            )
        ],
        [InlineKeyboardButton(text="⬅️ Back to Scheduler", callback_data="sec_scheduler")]
    ]

    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("sched_set_"))
async def cb_save_interval(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    parts = query.data.split("_")
    account_id = int(parts[2])
    hours = float(parts[3])

    async with AsyncSessionLocal() as session:
        await set_account_interval(session, account_id, hours)

    try:
        await query.answer(f"✅ Interval set to {hours} hours!", show_alert=True)
    except Exception:
        pass
    await cb_scheduler_menu(query)


@router.callback_query(F.data.startswith("sched_tog_acc_"))
async def cb_toggle_account_scheduler(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    account_id = int(query.data.split("_")[3])

    async with AsyncSessionLocal() as session:
        promo = await get_or_create_account_promo(session, account_id)
        new_state = not promo.is_enabled
        await set_account_campaign_enabled(session, account_id, new_state)

    try:
        await query.answer(f"Status changed to {'ENABLED' if new_state else 'DISABLED'}", show_alert=True)
    except Exception:
        pass
    await cb_scheduler_menu(query)


@router.callback_query(F.data == "sched_toggle_global")
async def cb_toggle_global_scheduler(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        curr = await get_setting(session, "broadcast_enabled", "true")
        new_val = "false" if curr.lower() == "true" else "true"
        await set_setting(session, "broadcast_enabled", new_val)

    try:
        await query.answer(f"Global Scheduler {'ENABLED' if new_val == 'true' else 'PAUSED'}", show_alert=True)
    except Exception:
        pass
    await cb_scheduler_menu(query)


@router.callback_query(F.data == "sched_toggle_spintax")
async def cb_toggle_spintax(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        curr = await get_setting(session, "spintax_enabled", "true")
        new_val = "false" if curr.lower() == "true" else "true"
        await set_setting(session, "spintax_enabled", new_val)

    try:
        await query.answer(f"Spintax Engine {'ENABLED' if new_val == 'true' else 'DISABLED'}", show_alert=True)
    except Exception:
        pass
    await cb_scheduler_menu(query)


@router.callback_query(F.data == "sched_preset_balanced")
async def cb_preset_balanced(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        await set_setting(session, "min_delay_sec", "18")
        await set_setting(session, "max_delay_sec", "35")
        await set_setting(session, "batch_size", "8")
        await set_setting(session, "batch_cooldown_sec", "240")

    try:
        await query.answer("⚡ Applied 'Balanced' Anti-Ban Preset (18–35s delay, 4m cooldown)", show_alert=True)
    except Exception:
        pass
    await cb_scheduler_menu(query)


@router.callback_query(F.data == "sched_preset_safe")
async def cb_preset_safe(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        await set_setting(session, "min_delay_sec", "25")
        await set_setting(session, "max_delay_sec", "45")
        await set_setting(session, "batch_size", "5")
        await set_setting(session, "batch_cooldown_sec", "300")

    try:
        await query.answer("🛡️ Applied 'Conservative Safe' Preset (25–45s delay, 5m cooldown)", show_alert=True)
    except Exception:
        pass
    await cb_scheduler_menu(query)
