import html
import re
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    get_groups_paginated,
    get_selected_groups,
    toggle_group_selection,
    select_all_groups,
    deselect_all_groups,
    sync_telegram_groups,
    get_group_stats_for_account,
    get_or_create_account_promo
)
from core.client import tg_manager
from core.broadcaster import broadcaster
import config

router = Router()


async def _safe_send_message(query: CallbackQuery, text: str, kb: list, is_edit: bool = True):
    markup = InlineKeyboardMarkup(inline_keyboard=kb)
    try:
        if is_edit:
            await query.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        else:
            await query.message.answer(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        # Fallback to plain text so keyboard buttons NEVER crash/freeze on HTML issues
        plain_text = re.sub(r'<[^>]+>', '', text)
        try:
            if is_edit:
                await query.message.edit_text(plain_text, reply_markup=markup)
            else:
                await query.message.answer(plain_text, reply_markup=markup)
        except Exception:
            pass


@router.callback_query(F.data == "sec_broadcast")
async def cb_broadcast_menu(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass
    if state:
        await state.clear()

    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        stats_map = {}
        for acc in accounts:
            st = await get_group_stats_for_account(session, acc.id)
            selected = await get_selected_groups(session, acc.id)
            stats_map[acc.id] = (st, len(selected))

    text = (
        "🚀 <b>BROADCAST CONTROLLER — SELECT NUMBER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select an account to configure, fetch joined groups via Telegram API, and start or stop campaigns:\n\n"
    )

    kb = []
    if not accounts:
        text += "<i>No accounts connected yet. Please add a phone number in 📱 Add Numbers.</i>"
    else:
        for acc in accounts:
            st, sel_count = stats_map[acc.id]
            is_running = broadcaster.is_account_broadcasting(acc.id)
            status_tag = "🔴 [RUNNING]" if is_running else "🟢 [IDLE]"
            user_lbl = html.escape(f"@{acc.username}" if acc.username else (acc.first_name or ""))
            text += (
                f"📱 <b>{acc.phone}</b> ({user_lbl}) {status_tag}\n"
                f"   • Selected for Broadcast: <code>{sel_count}/{st['ACTIVE']} groups</code>\n\n"
            )
            btn_text = f"🛑 Monitor/Stop {acc.phone}" if is_running else f"🚀 Start {acc.phone} ({sel_count} selected)"
            kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"bc_acc_{acc.id}")])

    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    await _safe_send_message(query, text, kb, is_edit=True)


@router.callback_query(F.data.startswith("bc_acc_"))
async def cb_account_broadcast_detail(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass
    if state:
        await state.clear()

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        acc = next((a for a in accounts if a.id == account_id), None)
        if not acc:
            return
        st = await get_group_stats_for_account(session, account_id)
        selected = await get_selected_groups(session, account_id)
        promo = await get_or_create_account_promo(session, account_id, acc.phone)

    is_running = broadcaster.is_account_broadcasting(account_id)
    raw_user = f"@{acc.username}" if acc.username else (acc.first_name or "")
    user_lbl = html.escape(raw_user)

    if is_running:
        status_info = broadcaster.get_progress_status(account_id)
        pct = status_info.get("progress_percent", 0.0)
        curr = status_info.get("current_index", 0)
        tot = status_info.get("total_targets", len(selected))
        bar_len = 10
        filled = int((pct / 100) * bar_len)
        bar = "▓" * filled + "░" * (bar_len - filled)
        elapsed_m = status_info.get("elapsed_seconds", 0) // 60
        elapsed_s = status_info.get("elapsed_seconds", 0) % 60

        text = (
            f"🔴 <b>BROADCAST IN PROGRESS — {acc.phone}</b> ({user_lbl})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<code>[{bar}]</code> {pct}%\n"
            f"🎯 Progress: <code>{curr}/{tot} groups</code>\n"
            f"⏱️ Elapsed Time: <code>{elapsed_m}m {elapsed_s}s</code>\n\n"
            f"📈 <b>Live Metrics:</b>\n"
            f"• ✅ Delivered: <code>{status_info.get('success_count', 0)}</code>\n"
            f"• ❌ Failed: <code>{status_info.get('failed_count', 0)}</code>\n"
            f"• ⏳ Slowmode: <code>{status_info.get('skipped_count', 0)}</code>\n\n"
            f"🛡️ <i>Anti-ban rate limiter is actively pacing deliveries.</i>"
        )
        kb = [
            [InlineKeyboardButton(text="🔄 Refresh Live Progress", callback_data=f"bc_acc_{account_id}")],
            [InlineKeyboardButton(text="🛑 STOP CAMPAIGN", callback_data=f"bc_stop_{account_id}")],
            [InlineKeyboardButton(text="⬅️ Back to Numbers List", callback_data="sec_broadcast")]
        ]
    else:
        # ── Auto-sync if this account has 0 groups (never synced yet) ─────────
        if st["TOTAL"] == 0:
            try:
                await query.message.edit_text(
                    f"⏳ <b>First-time sync for {acc.phone}...</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Fetching all joined groups directly from Telegram API.\n"
                    f"This takes 5–20 seconds depending on how many groups you've joined...",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            tg_groups = await tg_manager.fetch_joined_groups(account_id)
            async with AsyncSessionLocal() as session:
                sync_res = await sync_telegram_groups(session, account_id, tg_groups)
                st = await get_group_stats_for_account(session, account_id)
                selected = await get_selected_groups(session, account_id)

        clean_snippet = html.escape(re.sub(r'<[^>]+>', '', promo.text or "")[:50].strip())
        text = (
            f"🚀 <b>CAMPAIGN LAUNCHER — {acc.phone}</b> ({user_lbl})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Promotional Text:</b> <i>{clean_snippet}...</i>\n"
            f"🖼️ <b>Media Attached:</b> <code>{promo.media_type.upper()}</code>\n\n"
            f"🎯 <b>Target Groups:</b>\n"
            f"• ✅ Active Groups in DB: <b>{st['ACTIVE']}</b>\n"
            f"• ☑️ Selected for Broadcast: <b>{len(selected)}</b>\n\n"
            f"💡 <i>Tap <b>🔄 Sync from Telegram API</b> to re-fetch your latest joined groups.</i>"
        )
        kb = [
            [InlineKeyboardButton(text=f"🚀 START BROADCAST ({len(selected)} groups)", callback_data=f"bc_launch_{account_id}")],
            [
                InlineKeyboardButton(text="🔄 Sync from Telegram API", callback_data=f"bc_sync_{account_id}"),
                InlineKeyboardButton(text="📋 Select Groups", callback_data=f"bc_page_{account_id}_1")
            ],
            [InlineKeyboardButton(text="⬅️ Back to Numbers List", callback_data="sec_broadcast")]
        ]

    await _safe_send_message(query, text, kb, is_edit=True)


@router.callback_query(F.data.startswith("bc_sync_"))
async def cb_sync_telegram_groups(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    try:
        await query.message.edit_text(
            "⏳ <b>Querying Telegram API...</b>\n"
            "Fetching all joined groups & supergroups from your account dialogs. This may take 5–15 seconds...",
            parse_mode="HTML"
        )
    except Exception:
        pass

    tg_groups = await tg_manager.fetch_joined_groups(account_id)

    async with AsyncSessionLocal() as session:
        sync_res = await sync_telegram_groups(session, account_id, tg_groups)

    try:
        await query.message.answer(
            f"✅ <b>Telegram API Sync Complete!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 <b>New Groups Synced:</b> <code>{sync_res['added']}</code>\n"
            f"🔁 <b>Already in DB:</b> <code>{sync_res['existing']}</code>\n"
            f"🎯 <b>Total Active Groups:</b> <code>{sync_res['total']}</code>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await cb_account_broadcast_detail(query)


@router.callback_query(F.data.startswith("bc_page_"))
async def cb_group_selection_page(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    parts = query.data.split("_")
    account_id = int(parts[2])
    page = int(parts[3])

    async with AsyncSessionLocal() as session:
        groups, total_pages = await get_groups_paginated(session, account_id, page=page, per_page=10)
        selected = await get_selected_groups(session, account_id)
        st = await get_group_stats_for_account(session, account_id)

    text = (
        f"📋 <b>SELECT TARGET GROUPS (Page {page}/{total_pages})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Selected:</b> <code>{len(selected)}/{st['ACTIVE']} groups</code>\n"
        f"Tap any group below to toggle it ON/OFF for broadcasting:\n\n"
    )

    kb = []
    for g in groups:
        box = "☑️" if g.is_selected else "☐"
        title_display = g.title or g.identifier
        if len(title_display) > 28:
            title_display = title_display[:25] + "..."
        kb.append([
            InlineKeyboardButton(
                text=f"{box} {title_display}",
                callback_data=f"bc_tog_{account_id}_{g.id}_{page}"
            )
        ])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"bc_page_{account_id}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"bc_page_{account_id}_{page + 1}"))
    kb.append(nav_row)

    kb.append([
        InlineKeyboardButton(text="✅ Select All", callback_data=f"bc_selall_{account_id}_{page}"),
        InlineKeyboardButton(text="❌ Deselect All", callback_data=f"bc_deselall_{account_id}_{page}")
    ])
    kb.append([
        InlineKeyboardButton(text=f"🚀 Done & Launch ({len(selected)} selected)", callback_data=f"bc_acc_{account_id}")
    ])

    await _safe_send_message(query, text, kb, is_edit=True)


@router.callback_query(F.data.startswith("bc_tog_"))
async def cb_toggle_single_group(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    parts = query.data.split("_")
    account_id = int(parts[2])
    group_id = int(parts[3])
    page = int(parts[4])

    async with AsyncSessionLocal() as session:
        await toggle_group_selection(session, group_id)

    query.data = f"bc_page_{account_id}_{page}"
    await cb_group_selection_page(query)


@router.callback_query(F.data.startswith("bc_selall_"))
async def cb_select_all(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    parts = query.data.split("_")
    account_id = int(parts[2])
    page = int(parts[3])

    async with AsyncSessionLocal() as session:
        await select_all_groups(session, account_id)

    query.data = f"bc_page_{account_id}_{page}"
    await cb_group_selection_page(query)


@router.callback_query(F.data.startswith("bc_deselall_"))
async def cb_deselect_all(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    parts = query.data.split("_")
    account_id = int(parts[2])
    page = int(parts[3])

    async with AsyncSessionLocal() as session:
        await deselect_all_groups(session, account_id)

    query.data = f"bc_page_{account_id}_{page}"
    await cb_group_selection_page(query)


@router.callback_query(F.data.startswith("bc_launch_"))
async def cb_launch_account_broadcast(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        await set_account_campaign_enabled(session, account_id, True)

    res = await broadcaster.start_account_broadcast(account_id, trigger_type="MANUAL_ADMIN")

    if res.get("status") == "already_running":
        try:
            await query.answer("⚠️ Campaign is already actively running for this account!", show_alert=True)
        except Exception:
            pass
    elif res.get("status") == "no_groups":
        try:
            await query.answer("⚠️ No groups selected! Please select groups first or tap Sync from Telegram API.", show_alert=True)
        except Exception:
            pass
    elif res.get("status") == "not_authorized":
        try:
            await query.answer("❌ Account not authorized. Please re-login via 📱 Add Numbers.", show_alert=True)
        except Exception:
            pass

    await cb_account_broadcast_detail(query)


@router.callback_query(F.data.startswith("bc_stop_"))
async def cb_stop_account_broadcast(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    account_id = int(query.data.split("_")[2])
    broadcaster.stop_account_broadcast(account_id)
    async with AsyncSessionLocal() as session:
        await set_account_campaign_enabled(session, account_id, False)
    try:
        await query.answer("🛑 Campaign stop requested. Repeating auto-broadcast disabled.", show_alert=True)
    except Exception:
        pass
    await cb_account_broadcast_detail(query)


@router.callback_query(F.data == "noop")
async def cb_noop(query: CallbackQuery):
    try:
        await query.answer()
    except Exception:
        pass
