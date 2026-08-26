import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import AsyncSessionLocal
from database.crud import (
    bulk_add_groups,
    get_group_stats,
    get_all_groups,
    get_groups_by_status,
    reset_all_group_statuses,
    delete_all_groups_by_status
)
from core.joiner import safe_joiner
import config

router = Router(name="group_manager")

class GroupManagerStates(StatesGroup):
    waiting_for_bulk_links = State()

def get_group_manager_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="➕ Add / Bulk Import Groups", callback_data="groups_add_bulk"),
            InlineKeyboardButton(text="⚡ Run Safe Auto-Joiner", callback_data="groups_auto_join")
        ],
        [
            InlineKeyboardButton(text="📋 List & Stats", callback_data="groups_list_stats"),
            InlineKeyboardButton(text="🔄 Reset All to Active", callback_data="groups_reset_active")
        ],
        [
            InlineKeyboardButton(text="🧹 Purge Banned/Invalid", callback_data="groups_purge_banned")
        ],
        [
            InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "menu_groups")
async def cb_groups_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        stats = await get_group_stats(session)

    text = (
        "👥 <b>TARGET GROUPS MANAGER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Total Target Groups:</b> <code>{stats.get('TOTAL', 0)}</code>\n\n"
        f"• 🟢 Active & Ready: <code>{stats.get('ACTIVE', 0)}</code>\n"
        f"• ⏳ Slowmode Queued: <code>{stats.get('SLOWMODE', 0)}</code>\n"
        f"• 🔴 Banned by Admin: <code>{stats.get('BANNED', 0)}</code>\n"
        f"• ⚠️ Restricted / Read-Only: <code>{stats.get('RESTRICTED', 0)}</code>\n"
        f"• 🚫 Expired / Invalid Links: <code>{stats.get('INVALID_LINK', 0)}</code>\n\n"
        "💡 <i>You can paste up to 400+ group links or usernames at once!</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_group_manager_keyboard())
    await query.answer()

@router.callback_query(F.data == "groups_add_bulk")
async def cb_add_bulk_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.set_state(GroupManagerStates.waiting_for_bulk_links)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_groups")]
    ])
    
    text = (
        "➕ <b>BULK ADD / IMPORT GROUPS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Paste your group links or usernames below.\n"
        "You can send multiple lines, comma-separated, or space-separated!\n\n"
        "<b>Supported Formats:</b>\n"
        "• <code>@groupusername</code>\n"
        "• <code>https://t.me/groupusername</code>\n"
        "• <code>https://t.me/+join_hash_code</code>\n"
        "• <code>-1001234567890</code> (Chat ID)\n\n"
        "<i>Paste your group links now (up to 400+):</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb)
    await query.answer()

@router.message(GroupManagerStates.waiting_for_bulk_links)
async def handle_bulk_groups_input(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    raw_text = message.text or ""
    if not raw_text.strip():
        await message.answer("⚠️ Please send text containing group links or usernames.")
        return

    # Split lines and whitespace
    raw_lines = raw_text.replace(",", "\n").splitlines()
    cleaned = []
    for line in raw_lines:
        tokens = line.strip().split()
        for token in tokens:
            t = token.strip()
            if t:
                cleaned.append(t)

    if not cleaned:
        await message.answer("⚠️ No valid group identifiers found. Try again.")
        return

    status_msg = await message.answer(f"⏳ <i>Processing and validating {len(cleaned)} groups...</i>", parse_mode="HTML")

    async with AsyncSessionLocal() as session:
        added, existing = await bulk_add_groups(session, cleaned)
        stats = await get_group_stats(session)

    await state.clear()
    
    res_text = (
        "🎉 <b>Bulk Import Completed!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Newly Added:</b> {added}\n"
        f"🔁 <b>Already Existing (Skipped):</b> {existing}\n"
        f"📈 <b>Total Groups in Bot:</b> {stats.get('TOTAL', 0)}\n\n"
        "💡 <i>If these are private groups your userbot has not joined yet, tap <b>'Run Safe Auto-Joiner'</b> to automatically join them with anti-ban safeguards.</i>"
    )
    await status_msg.edit_text(res_text, parse_mode="HTML", reply_markup=get_group_manager_keyboard())

@router.callback_query(F.data == "groups_auto_join")
async def cb_run_auto_joiner(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    if safe_joiner.is_running:
        await query.answer("Auto-joiner is already running in background!", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        groups = await get_all_groups(session)

    if not groups:
        await query.answer("No groups found in database. Add groups first.", show_alert=True)
        return

    await query.message.answer(
        f"⚡ <b>Safe Auto-Joiner Started!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Total Targets:</b> {len(groups)}\n"
        f"🛡️ <b>Anti-Ban Delay:</b> 45s - 90s between joins\n"
        f"<i>The bot will join in the background and notify you when finished.</i>",
        parse_mode="HTML"
    )
    await query.answer()

    # Run in background task
    asyncio.create_task(safe_joiner.join_bulk_groups_safely(groups))

@router.callback_query(F.data == "groups_list_stats")
async def cb_list_stats(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        stats = await get_group_stats(session)
        sample_active = await get_groups_by_status(session, "ACTIVE")
        sample_banned = await get_groups_by_status(session, "BANNED")
        sample_restricted = await get_groups_by_status(session, "RESTRICTED")

    active_list = "\n".join([f"• <code>{g.identifier}</code>" for g in sample_active[:8]]) or "<i>None</i>"
    failed_list = "\n".join([f"• <code>{g.identifier}</code> ({g.last_error or 'Banned'})" for g in (sample_banned + sample_restricted)[:8]]) or "<i>None</i>"

    text = (
        "📋 <b>GROUP DATABASE BREAKDOWN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Total Count:</b> <code>{stats.get('TOTAL', 0)}</code>\n\n"
        "🟢 <b>Active Sample (Ready to send):</b>\n"
        f"{active_list}\n\n"
        "🔴 <b>Banned / Restricted Sample:</b>\n"
        f"{failed_list}\n"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Groups", callback_data="menu_groups")]
    ])
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb)
    await query.answer()

@router.callback_query(F.data == "groups_reset_active")
async def cb_reset_active(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        updated = await reset_all_group_statuses(session)

    await query.answer(f"Reset {updated} groups to ACTIVE status!", show_alert=True)
    # Refresh menu
    await cb_groups_menu(query, None)

@router.callback_query(F.data == "groups_purge_banned")
async def cb_purge_banned(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    async with AsyncSessionLocal() as session:
        d1 = await delete_all_groups_by_status(session, "BANNED")
        d2 = await delete_all_groups_by_status(session, "INVALID_LINK")
        d3 = await delete_all_groups_by_status(session, "RESTRICTED")

    total_deleted = d1 + d2 + d3
    await query.answer(f"Purged {total_deleted} invalid/banned groups from database.", show_alert=True)
    await cb_groups_menu(query, None)
