import asyncio
import os
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    get_all_account_campaigns,
    get_or_create_account_promo,
    update_account_promo,
    set_account_interval,
    get_active_groups
)
from core.broadcaster import broadcaster
from core.client import tg_manager
import config

router = Router(name="campaign_manager")

class CampaignStates(StatesGroup):
    waiting_for_account_promo_text = State()
    waiting_for_account_promo_media = State()

async def render_campaigns_dashboard(target, account_id_highlight: int = None):
    async with AsyncSessionLocal() as session:
        pairs = await get_all_account_campaigns(session)
        groups = await get_active_groups(session)

    if not pairs:
        text = (
            "📢 <b>MULTI-AD CAMPAIGNS DASHBOARD</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚠️ <b>No phone numbers found!</b>\n\n"
            "To run ads from multiple numbers, please add your phone numbers first via /menu ➡️ 📱 Switch / Add Number."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add Phone Number Now", callback_data="auth_start_login")],
            [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")]
        ])
        if isinstance(target, CallbackQuery):
            try:
                await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            except TelegramBadRequest:
                pass
            await target.answer()
        else:
            await target.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    text = (
        "📢 <b>MULTI-ACCOUNT SIMULTANEOUS ADS DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Ready Target Groups:</b> <code>{len(groups)}</code>\n"
        f"📱 <b>Connected Phone Numbers:</b> <code>{len(pairs)} accounts</code>\n\n"
        "<i>Each number has its own dedicated ad message & anti-ban worker:</i>\n\n"
    )

    kb = []
    any_running = False

    for idx, (acc, promo) in enumerate(pairs, 1):
        is_running = broadcaster.is_account_broadcasting(acc.id)
        if is_running:
            any_running = True
            progress = broadcaster.get_progress_status(acc.id)
            status_badge = f"🚀 <b>RUNNING</b> ({progress.get('current_index', 0)}/{progress.get('total_targets', len(groups))} — {progress.get('progress_percent', 0)}%)"
        else:
            status_badge = "🟢 <b>READY / IDLE</b>"

        prem_badge = "👑 Premium" if acc.is_premium else "Standard"
        media_tag = f"[{promo.media_type.upper()}]" if promo.media_type != "none" else "[TEXT ONLY]"
        
        # Snippet of message
        clean_text = promo.text.replace("<", "&lt;").replace(">", "&gt;")
        snippet = (clean_text[:65] + "...") if len(clean_text) > 65 else clean_text

        text += (
            f"<b>{idx}. 📱 {acc.phone}</b> (@{acc.username or acc.first_name or 'NoUser'}) — {prem_badge}\n"
            f"   • <b>Status:</b> {status_badge}\n"
            f"   • <b>Ad:</b> {media_tag} <i>{snippet}</i>\n"
            f"   • <b>Interval:</b> Every {promo.interval_hours} Hours\n\n"
        )

        # Action row for this account
        if is_running:
            kb.append([
                InlineKeyboardButton(text=f"🛑 Stop #{idx} ({acc.phone[-4:]})", callback_data=f"cmp_stop_{acc.id}"),
                InlineKeyboardButton(text=f"📡 Monitor #{idx}", callback_data=f"cmp_mon_{acc.id}")
            ])
        else:
            kb.append([
                InlineKeyboardButton(text=f"🚀 Launch #{idx} ({acc.phone[-4:]})", callback_data=f"cmp_start_{acc.id}"),
                InlineKeyboardButton(text=f"✏️ Edit Ad #{idx}", callback_data=f"cmp_edit_{acc.id}")
            ])

    # Global Launch / Stop All Rows
    if any_running:
        kb.append([InlineKeyboardButton(text="🛑 Force Stop ALL Running Ads", callback_data="cmp_stop_all")])
    else:
        kb.append([InlineKeyboardButton(text="🚀 Launch ALL Numbers Simultaneously", callback_data="cmp_start_all")])

    kb.append([
        InlineKeyboardButton(text="➕ Add Another Phone Number", callback_data="auth_start_login"),
        InlineKeyboardButton(text="🔄 Refresh Dashboard", callback_data="menu_campaigns")
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])

    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except TelegramBadRequest:
            pass
        await target.answer()
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.message(Command("campaigns"))
async def cmd_campaigns(message: Message, state: FSMContext = None):
    if not config.is_admin(message.from_user.id):
        return
    if state is not None:
        await state.clear()
    await render_campaigns_dashboard(message)

@router.callback_query(F.data == "menu_campaigns")
async def cb_campaigns_dashboard(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    if state is not None:
        await state.clear()
    await render_campaigns_dashboard(query)

@router.callback_query(F.data == "cmp_start_all")
async def cb_start_all_campaigns(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    res = await broadcaster.start_all_campaigns(trigger_type="MANUAL_ALL")
    started = res.get("started", 0)
    await query.answer(f"🚀 Launched {started} campaigns in parallel!", show_alert=True)
    await render_campaigns_dashboard(query)

@router.callback_query(F.data == "cmp_stop_all")
async def cb_stop_all_campaigns(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    broadcaster.stop_all_campaigns()
    await query.answer("🛑 Stopped all running campaigns.", show_alert=True)
    await render_campaigns_dashboard(query)

@router.callback_query(F.data.startswith("cmp_start_"))
async def cb_start_single_campaign(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_start_", ""))
    res = await broadcaster.start_account_broadcast(acc_id, trigger_type="MANUAL_ADMIN")
    if res.get("status") == "started":
        await query.answer(f"🚀 Launched campaign for {res.get('phone')}!", show_alert=True)
    elif res.get("status") == "already_running":
        await query.answer("This account is already actively broadcasting!", show_alert=True)
    else:
        await query.answer(f"Error: {res.get('reason', 'Could not start')}", show_alert=True)
    await render_campaigns_dashboard(query)

@router.callback_query(F.data.startswith("cmp_stop_"))
async def cb_stop_single_campaign(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_stop_", ""))
    broadcaster.stop_account_broadcast(acc_id)
    await query.answer("Stopped campaign for this account.", show_alert=True)
    await render_campaigns_dashboard(query)

@router.callback_query(F.data.startswith("cmp_mon_"))
async def cb_campaign_monitor(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_mon_", ""))
    progress = broadcaster.get_progress_status(acc_id)
    if not progress.get("is_running"):
        await query.answer("This campaign is not currently running.", show_alert=True)
        return

    bar_len = 14
    filled = int((progress["current_index"] / max(progress["total_targets"], 1)) * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    mins = progress["elapsed_seconds"] // 60
    secs = progress["elapsed_seconds"] % 60

    text = (
        f"📡 <b>LIVE MONITOR — {progress.get('account_phone')}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Progress:</b> <code>[{bar}] {progress['progress_percent']}%</code>\n\n"
        f"• <b>Current Target:</b> <code>{progress['current_index']} / {progress['total_targets']}</code>\n"
        f"• ✅ <b>Delivered:</b> <code>{progress['success_count']} groups</code>\n"
        f"• ❌ <b>Failed / Banned:</b> <code>{progress['failed_count']} groups</code>\n"
        f"• ⏱️ <b>Elapsed:</b> <code>{mins}m {secs}s</code>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh Monitor", callback_data=f"cmp_mon_{acc_id}")],
        [InlineKeyboardButton(text="🛑 Stop This Campaign", callback_data=f"cmp_stop_{acc_id}")],
        [InlineKeyboardButton(text="⬅️ Back to Campaigns", callback_data="menu_campaigns")]
    ])
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        pass
    await query.answer()

# ==================== EDIT PROMO AD FOR SPECIFIC ACCOUNT ====================

@router.callback_query(F.data.startswith("cmp_edit_"))
async def cb_edit_account_promo_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_edit_", ""))
    await state.clear()
    await state.update_data(target_account_id=acc_id)

    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        acc = next((a for a in accounts if a.id == acc_id), None)
        promo = await get_or_create_account_promo(session, acc_id, acc.phone if acc else None)

    media_badge = f"📷 Photo Attached" if promo.media_type == "photo" else ("🎥 Video Attached" if promo.media_type == "video" else "📝 Text Only")

    text = (
        f"✏️ <b>EDIT AD FOR: {acc.phone if acc else f'Account #{acc_id}'}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Current Media:</b> <code>{media_badge}</code>\n"
        f"<b>Current Interval:</b> <code>Every {promo.interval_hours} Hours</code>\n\n"
        "<b>Current Text Preview:</b>\n"
        f"{promo.text}\n\n"
        "<i>To change this ad, choose an option below:</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Edit Text / Caption", callback_data=f"cmp_txt_{acc_id}"),
            InlineKeyboardButton(text="🖼️ Attach Photo/Video", callback_data=f"cmp_med_{acc_id}")
        ],
        [
            InlineKeyboardButton(text="⏱️ Change Repeat Interval", callback_data=f"cmp_int_{acc_id}"),
            InlineKeyboardButton(text="🗑️ Remove Media", callback_data=f"cmp_rm_med_{acc_id}")
        ],
        [InlineKeyboardButton(text="⬅️ Back to Campaigns", callback_data="menu_campaigns")]
    ])
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        pass
    await query.answer()

@router.callback_query(F.data.startswith("cmp_txt_"))
async def cb_edit_acc_text_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_txt_", ""))
    await state.update_data(target_account_id=acc_id)
    await state.set_state(CampaignStates.waiting_for_account_promo_text)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cmp_edit_{acc_id}")]
    ])
    await query.message.edit_text(
        "📝 <b>Send New Promotional Text / Spintax:</b>\n\n"
        "Type or paste your new promotional message below (HTML formatting and Spintax like <code>{Hello|Hi|Hey}</code> supported):",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await query.answer()

@router.message(CampaignStates.waiting_for_account_promo_text, F.text)
async def handle_account_promo_text(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    data = await state.get_data()
    acc_id = data.get("target_account_id")
    if not acc_id:
        await message.answer("Session expired. Please re-open /campaigns.")
        await state.clear()
        return

    new_text = message.text.strip()
    async with AsyncSessionLocal() as session:
        promo = await update_account_promo(session, acc_id, text=new_text)

    await state.clear()
    await message.answer("✅ <b>Ad text updated successfully for this account!</b>", parse_mode="HTML")
    await render_campaigns_dashboard(message)

@router.callback_query(F.data.startswith("cmp_med_"))
async def cb_edit_acc_media_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_med_", ""))
    await state.update_data(target_account_id=acc_id)
    await state.set_state(CampaignStates.waiting_for_account_promo_media)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cmp_edit_{acc_id}")]
    ])
    await query.message.edit_text(
        "🖼️ <b>Send Photo or Video:</b>\n\n"
        "Send your promotional Photo or Video directly into this chat (you can also include a caption):",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await query.answer()

@router.message(CampaignStates.waiting_for_account_promo_media, F.photo | F.video)
async def handle_account_promo_media(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    data = await state.get_data()
    acc_id = data.get("target_account_id")
    if not acc_id:
        await message.answer("Session expired. Please re-open /campaigns.")
        await state.clear()
        return

    os.makedirs(config.MEDIA_STORAGE_PATH, exist_ok=True)
    caption_text = message.caption or ""

    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_info = await message.bot.get_file(file_id)
        local_path = os.path.join(config.MEDIA_STORAGE_PATH, f"acc_{acc_id}_promo.jpg")
        await message.bot.download_file(file_info.file_path, local_path)
        media_type = "photo"
    else:
        video = message.video
        file_id = video.file_id
        file_info = await message.bot.get_file(file_id)
        local_path = os.path.join(config.MEDIA_STORAGE_PATH, f"acc_{acc_id}_promo.mp4")
        await message.bot.download_file(file_info.file_path, local_path)
        media_type = "video"

    async with AsyncSessionLocal() as session:
        cur_promo = await get_or_create_account_promo(session, acc_id)
        final_text = caption_text if caption_text else cur_promo.text
        await update_account_promo(
            session=session,
            account_id=acc_id,
            text=final_text,
            media_type=media_type,
            media_file_id=file_id,
            media_path=local_path
        )

    await state.clear()
    await message.answer("✅ <b>Media & Caption saved for this account!</b>", parse_mode="HTML")
    await render_campaigns_dashboard(message)

@router.callback_query(F.data.startswith("cmp_rm_med_"))
async def cb_remove_acc_media(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_rm_med_", ""))
    async with AsyncSessionLocal() as session:
        cur = await get_or_create_account_promo(session, acc_id)
        await update_account_promo(
            session=session,
            account_id=acc_id,
            text=cur.text,
            media_type="none",
            media_file_id=None,
            media_path=None
        )
    await query.answer("Removed media attachment. Ad is now Text Only.", show_alert=True)
    await cb_edit_account_promo_menu(query, None)

@router.callback_query(F.data.startswith("cmp_int_"))
async def cb_change_acc_interval_menu(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("cmp_int_", ""))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏱️ 1.0h", callback_data=f"cmp_setint_{acc_id}_1.0"),
            InlineKeyboardButton(text="⏱️ 1.5h", callback_data=f"cmp_setint_{acc_id}_1.5"),
            InlineKeyboardButton(text="⏱️ 2.0h", callback_data=f"cmp_setint_{acc_id}_2.0")
        ],
        [
            InlineKeyboardButton(text="⏱️ 3.0h", callback_data=f"cmp_setint_{acc_id}_3.0"),
            InlineKeyboardButton(text="⏱️ 4.0h", callback_data=f"cmp_setint_{acc_id}_4.0"),
            InlineKeyboardButton(text="⏱️ 6.0h", callback_data=f"cmp_setint_{acc_id}_6.0")
        ],
        [InlineKeyboardButton(text="⬅️ Back to Ad Editor", callback_data=f"cmp_edit_{acc_id}")]
    ])
    text = f"⏱️ <b>Select Repeat Interval for this Number:</b>"
    try:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        pass
    await query.answer()

@router.callback_query(F.data.startswith("cmp_setint_"))
async def cb_save_acc_interval(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    parts = query.data.replace("cmp_setint_", "").split("_")
    acc_id = int(parts[0])
    hours = float(parts[1])
    async with AsyncSessionLocal() as session:
        await set_account_interval(session, acc_id, hours)
    await query.answer(f"Interval set to every {hours} hours!", show_alert=True)
    await cb_edit_account_promo_menu(query, None)
