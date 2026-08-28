import io
import re
import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    bulk_add_groups_for_account,
    get_groups_for_account,
    get_unjoined_groups_for_account,
    get_group_stats_for_account,
    get_join_report,
    get_join_logs,
    check_daily_join_limit,
    smart_clean_groups_for_account
)
from core.joiner import safe_joiner
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
        plain_text = re.sub(r'<[^>]+>', '', text)
        try:
            if is_edit:
                await query.message.edit_text(plain_text, reply_markup=markup)
            else:
                await query.message.answer(plain_text, reply_markup=markup)
        except Exception:
            pass


class JoinerStates(StatesGroup):
    waiting_for_links = State()


@router.callback_query(F.data == "sec_joiner")
async def cb_group_joiner_menu(query: CallbackQuery, state: FSMContext = None):
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
            unjoined = await get_unjoined_groups_for_account(session, acc.id)
            stats_map[acc.id] = (st, len(unjoined))

    text = (
        "👥 <b>GROUP JOINER — SELECT SENDER NUMBER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select the phone number you want to import and join groups with:\n\n"
    )

    kb = []
    if not accounts:
        text += "<i>No phone numbers connected. Please add a number first in 📱 Add Numbers.</i>"
    else:
        for acc in accounts:
            st, unjoined_count = stats_map[acc.id]
            user_lbl = html.escape(f"@{acc.username}" if acc.username else (acc.first_name or ""))
            text += (
                f"📱 <b>{acc.phone}</b> ({user_lbl})\n"
                f"   • Total Groups: <code>{st['TOTAL']}</code> (Active: {st['ACTIVE']})\n"
                f"   • Unjoined: <code>{unjoined_count}</code>\n\n"
            )
            kb.append([
                InlineKeyboardButton(
                    text=f"📱 {acc.phone} ({st['TOTAL']} groups | {unjoined_count} pending)",
                    callback_data=f"join_acc_{acc.id}"
                )
            ])

    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    await _safe_send_message(query, text, kb, is_edit=True)


@router.callback_query(F.data.startswith("join_acc_"))
async def cb_join_account_dashboard(query: CallbackQuery, state: FSMContext = None):
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
        unjoined = await get_unjoined_groups_for_account(session, account_id)
        report = await get_join_report(session, account_id)
        limit_info = await check_daily_join_limit(session, account_id)

    user_lbl = html.escape(f"@{acc.username}" if acc.username else (acc.first_name or ""))
    text = (
        f"👥 <b>GROUP JOINER — {acc.phone}</b> ({user_lbl})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Group Database Stats:</b>\n"
        f"• Total Saved: <code>{st['TOTAL']} groups</code>\n"
        f"• Active / Valid: <code>{st['ACTIVE']} groups</code>\n"
        f"• Unjoined (Pending): <code>{len(unjoined)} groups</code>\n\n"
        f"🛡️ <b>Anti-Ban Join Limits:</b>\n"
        f"• Joins Used Today: <code>{limit_info['used']}/{limit_info['limit']}</code> (Remaining: <b>{limit_info['remaining']}</b>)\n"
        f"• Max per session: <code>{config.MAX_JOINS_PER_SESSION} groups</code> (then 15m cooldown)\n"
        f"• Delay per join: <code>{config.MIN_JOIN_DELAY}s–{config.MAX_JOIN_DELAY}s</code>\n\n"
        f"📋 <b>All-Time Join Report:</b>\n"
        f"• ✅ Successfully Joined: <code>{report['JOINED']}</code>\n"
        f"• ⏳ Already Member: <code>{report['ALREADY_MEMBER']}</code>\n"
        f"• ❌ Failed / Expired: <code>{report['FAILED']}</code>\n"
    )

    kb = [
        [InlineKeyboardButton(text="📥 Import Group Links", callback_data=f"join_import_{account_id}")],
    ]

    if safe_joiner.is_running:
        kb.append([InlineKeyboardButton(text="🛑 Stop Current Auto-Joiner", callback_data=f"join_stop_{account_id}")])
    else:
        if len(unjoined) > 0 and limit_info["remaining"] > 0:
            kb.append([InlineKeyboardButton(text=f"⚡ Auto-Join {len(unjoined)} Groups", callback_data=f"join_run_{account_id}")])

    kb.append([
        InlineKeyboardButton(text="📋 Full Join Logs", callback_data=f"join_logs_{account_id}"),
        InlineKeyboardButton(text="🧹 Clean Dead Links", callback_data=f"join_clean_{account_id}")
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Numbers List", callback_data="sec_joiner")])

    await _safe_send_message(query, text, kb, is_edit=True)


@router.callback_query(F.data.startswith("join_import_"))
async def cb_join_import_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])
    await state.set_state(JoinerStates.waiting_for_links)
    await state.update_data(target_account_id=account_id)

    text = (
        "📥 <b>IMPORT GROUP LINKS / USERNAMES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Paste your list of Telegram groups below.\n\n"
        "<b>Supported Formats:</b>\n"
        "• <code>@public_group_username</code>\n"
        "• <code>https://t.me/joinchat/AAAAAF...</code> (Private Invite)\n"
        "• <code>https://t.me/+AbCdEf123...</code> (New Invite Link)\n"
        "• <code>https://t.me/group_username</code>\n\n"
        "💡 <i>You can paste up to 1,000 links in one message (separated by space, comma, or newline). Duplicates and invalid words are automatically filtered!</i>"
    )
    kb = [[InlineKeyboardButton(text="❌ Cancel", callback_data=f"join_acc_{account_id}")]]
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.message(JoinerStates.waiting_for_links)
async def handle_bulk_links_input(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    account_id = data.get("target_account_id")
    await state.clear()

    raw_text = message.text or ""
    tokens = re.split(r'[\s,\n]+', raw_text.strip())

    async with AsyncSessionLocal() as session:
        added_count, existing_count = await bulk_add_groups_for_account(session, account_id, tokens)
        st = await get_group_stats_for_account(session, account_id)
        unjoined = await get_unjoined_groups_for_account(session, account_id)

    text = (
        "✅ <b>GROUPS IMPORT COMPLETED!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>New Groups Added:</b> <code>{added_count}</code>\n"
        f"🔁 <b>Duplicates Skipped:</b> <code>{existing_count}</code>\n"
        f"🎯 <b>Total Active in DB:</b> <code>{st['ACTIVE']}</code>\n"
        f"⏳ <b>Pending Unjoined:</b> <code>{len(unjoined)}</code>\n\n"
        "<i>You can now start auto-joining them safely using the button below.</i>"
    )
    kb = [
        [InlineKeyboardButton(text=f"⚡ Start Auto-Joining ({len(unjoined)} pending)", callback_data=f"join_run_{account_id}")],
        [InlineKeyboardButton(text="👥 Back to Joiner Menu", callback_data=f"join_acc_{account_id}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("join_run_"))
async def cb_run_auto_joiner(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    if safe_joiner.is_running:
        try:
            await query.message.answer("⚠️ Auto-joiner is already running in background!")
        except Exception:
            pass
        return

    status_msg = await query.message.answer(
        "⚡ <b>Auto-Joiner Initializing...</b>\n"
        "Anti-ban safety delays enabled (25s–50s per join, max 40 per session).",
        parse_mode="HTML"
    )

    async def update_ui(current, total, joined, failed, group_info):
        try:
            pct = round((current / max(total, 1)) * 100, 1)
            bar_len = 10
            filled = int((pct / 100) * bar_len)
            bar = "▓" * filled + "░" * (bar_len - filled)
            txt = (
                f"⚡ <b>AUTO-JOIN IN PROGRESS ({pct}%)</b>\n"
                f"<code>[{bar}]</code> {current}/{total}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• ✅ <b>Joined:</b> <code>{joined}</code>\n"
                f"• ❌ <b>Failed:</b> <code>{failed}</code>\n"
                f"• 🎯 <b>Current Target:</b> <code>{group_info}</code>\n\n"
                f"🛡️ <i>Random jitter active to prevent Telegram flood bans.</i>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛑 Stop Auto-Join", callback_data=f"join_stop_{account_id}")]
            ])
            await status_msg.edit_text(txt, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    import asyncio
    asyncio.create_task(_run_joiner_task(account_id, status_msg, update_ui))


async def _run_joiner_task(account_id: int, status_msg: Message, update_ui):
    res = await safe_joiner.auto_join_for_account(account_id, progress_callback=update_ui)

    async with AsyncSessionLocal() as session:
        report = await get_join_report(session, account_id)
        limit_info = await check_daily_join_limit(session, account_id)

    status_str = "🛑 Stopped by User" if res.get("status") == "stopped" else "🎉 Completed"
    final_text = (
        f"📋 <b>AUTO-JOIN SESSION SUMMARY ({status_str})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>Targets Processed:</b> <code>{res.get('total', 0)}</code>\n"
        f"✅ <b>Successfully Joined:</b> <code>{res.get('joined', 0)}</code>\n"
        f"⏳ <b>Already Member:</b> <code>{res.get('already_member', 0)}</code>\n"
        f"❌ <b>Failed:</b> <code>{res.get('failed', 0)}</code>\n\n"
        f"📊 <b>Today's Total Joins:</b> <code>{limit_info['used']}/{limit_info['limit']}</code>\n"
        f"🛡️ <i>Detailed results recorded in Join Logs.</i>"
    )
    kb = [
        [InlineKeyboardButton(text="📋 View Join Logs", callback_data=f"join_logs_{account_id}")],
        [InlineKeyboardButton(text="👥 Back to Joiner", callback_data=f"join_acc_{account_id}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    try:
        await status_msg.edit_text(final_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("join_stop_"))
async def cb_stop_joiner(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    safe_joiner.stop_joiner()
    try:
        await query.answer("🛑 Stopping auto-joiner after current group...", show_alert=True)
    except Exception:
        pass


@router.callback_query(F.data.startswith("join_logs_"))
async def cb_view_join_logs(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        report = await get_join_report(session, account_id)
        failed_logs = await get_join_logs(session, account_id, limit=10, status_filter="FAILED")

    text = (
        f"📋 <b>JOIN REPORT & AUDIT — ACCOUNT #{account_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>Total Join Attempts:</b> <code>{report['TOTAL']}</code>\n"
        f"✅ <b>Successfully Joined:</b> <code>{report['JOINED']}</code>\n"
        f"⏳ <b>Already a Member:</b> <code>{report['ALREADY_MEMBER']}</code>\n"
        f"❌ <b>Failed / Invalid:</b> <code>{report['FAILED']}</code>\n\n"
    )

    if failed_logs:
        text += "⚠️ <b>Recent Failed Attempts (Sample):</b>\n"
        for log in failed_logs:
            err = log.error_reason or "Unknown Error"
            text += f"• <code>{log.identifier}</code>: <i>{err[:40]}</i>\n"
    else:
        text += "<i>No recent failed join records!</i>\n"

    kb = [
        [InlineKeyboardButton(text="📄 Export All Failed as TXT", callback_data=f"join_export_{account_id}")],
        [InlineKeyboardButton(text="🧹 Clean Failed Links from DB", callback_data=f"join_clean_{account_id}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data=f"join_acc_{account_id}")]
    ]
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("join_export_"))
async def cb_export_join_failures(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        failed_logs = await get_join_logs(session, account_id, limit=500, status_filter="FAILED")

    if not failed_logs:
        try:
            await query.answer("No failed join records to export!", show_alert=True)
        except Exception:
            pass
        return

    content = f"JOIN FAILURE AUDIT REPORT — Account #{account_id}\n" + "=" * 50 + "\n\n"
    for log in failed_logs:
        content += f"{log.identifier} | Error: {log.error_reason or 'N/A'} | Date: {log.joined_at}\n"

    file_bytes = io.BytesIO(content.encode("utf-8"))
    file_bytes.name = f"join_failures_account_{account_id}.txt"
    input_file = BufferedInputFile(file_bytes.getvalue(), filename=file_bytes.name)

    await query.message.answer_document(
        document=input_file,
        caption=f"📄 Exported {len(failed_logs)} failed join attempts."
    )


@router.callback_query(F.data.startswith("join_clean_"))
async def cb_clean_join_failures(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        res = await smart_clean_groups_for_account(session, account_id)

    try:
        await query.answer(f"🧹 Cleaned {res['deleted']} dead/banned links! {res['active']} active remaining.", show_alert=True)
    except Exception:
        pass
    await cb_join_account_dashboard(query)
