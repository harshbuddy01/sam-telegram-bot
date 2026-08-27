import io
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    get_join_report,
    get_join_logs,
    check_daily_join_limit,
    get_group_stats_for_account,
    get_recent_cycles,
    get_cycle_by_id,
    get_cycle_failed_logs,
    smart_clean_groups_for_account
)
from core.broadcaster import broadcaster
import config

router = Router()


@router.callback_query(F.data == "sec_reports")
async def cb_reports_menu(query: CallbackQuery, state: FSMContext = None):
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

    text = (
        "📊 <b>REPORTS & AUDIT DASHBOARD — SELECT NUMBER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select a phone number to view its comprehensive join and broadcast delivery audit logs:\n\n"
    )

    kb = []
    if not accounts:
        text += "<i>No phone numbers connected yet.</i>"
    else:
        for acc in accounts:
            user_lbl = f"@{acc.username}" if acc.username else (acc.first_name or "")
            is_active_bc = broadcaster.is_account_broadcasting(acc.id)
            live_tag = " 🔴 [LIVE BROADCASTING]" if is_active_bc else ""
            text += f"📱 <b>{acc.phone}</b> ({user_lbl}){live_tag}\n"
            kb.append([
                InlineKeyboardButton(
                    text=f"📊 Reports for {acc.phone}",
                    callback_data=f"rpt_acc_{acc.id}"
                )
            ])

    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("rpt_acc_"))
async def cb_account_report_detail(query: CallbackQuery, state: FSMContext = None):
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
        join_rep = await get_join_report(session, account_id)
        daily = await check_daily_join_limit(session, account_id)
        cycles = await get_recent_cycles(session, limit=5, account_id=account_id)

    user_lbl = f"@{acc.username}" if acc.username else (acc.first_name or "")
    text = (
        f"📊 <b>DETAILED AUDIT REPORT — {acc.phone}</b> ({user_lbl})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Group Joiner Stats:</b>\n"
        f"• Total Saved Groups: <code>{st['TOTAL']}</code> (Active: <code>{st['ACTIVE']}</code>)\n"
        f"• Successfully Joined: <code>{join_rep['JOINED']}</code>\n"
        f"• Already Member: <code>{join_rep['ALREADY_MEMBER']}</code>\n"
        f"• Join Failures: <code>{join_rep['FAILED']}</code>\n"
        f"• Today's Limit Used: <code>{daily['used']}/{daily['limit']}</code> (Remaining: <b>{daily['remaining']}</b>)\n\n"
        f"🚀 <b>Recent Broadcast Cycles:</b>\n"
    )

    if not cycles:
        text += "<i>No broadcast cycles recorded yet for this number.</i>\n"
    else:
        for c in cycles:
            st_emoji = "✅" if c.status == "COMPLETED" else ("🛑" if c.status == "STOPPED" else "⏳")
            duration_str = f"{c.duration_seconds // 60}m {c.duration_seconds % 60}s" if c.duration_seconds else "N/A"
            dt_str = c.started_at.strftime("%b %d, %H:%M UTC") if c.started_at else "N/A"
            text += (
                f"{st_emoji} <b>Cycle #{c.id}</b> ({dt_str})\n"
                f"   • Targets: <code>{c.total_targets}</code> | Delivered: <code>{c.success_count}</code> | Failed: <code>{c.failed_count}</code>\n"
                f"   • Duration: <code>{duration_str}</code> | Status: <code>{c.status}</code>\n"
            )

    kb = []
    if cycles:
        cycle_row = []
        for c in cycles[:3]:
            cycle_row.append(InlineKeyboardButton(text=f"🔍 Cycle #{c.id}", callback_data=f"rpt_cycle_{c.id}"))
        kb.append(cycle_row)

    kb.append([
        InlineKeyboardButton(text="📄 Export Recent Failures (TXT)", callback_data=f"rpt_export_{account_id}"),
        InlineKeyboardButton(text="🧹 Smart Clean Dead Links", callback_data=f"rpt_clean_{account_id}")
    ])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Reports List", callback_data="sec_reports")])

    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("rpt_cycle_"))
async def cb_cycle_drilldown(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    cycle_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        cycle = await get_cycle_by_id(session, cycle_id)
        if not cycle:
            return
        failed_logs = await get_cycle_failed_logs(session, cycle_id)

    duration_str = f"{cycle.duration_seconds // 60}m {cycle.duration_seconds % 60}s" if cycle.duration_seconds else "N/A"
    text = (
        f"🔍 <b>CYCLE #{cycle.id} AUDIT DRILL-DOWN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📱 <b>Sender Account:</b> {cycle.account_phone or 'N/A'}\n"
        f"📊 <b>Status:</b> <code>{cycle.status}</code>\n"
        f"⏱️ <b>Duration:</b> {duration_str}\n"
        f"🎯 <b>Total Targets:</b> {cycle.total_targets}\n"
        f"✅ <b>Delivered:</b> {cycle.success_count}\n"
        f"❌ <b>Failed / Banned:</b> {cycle.failed_count}\n"
        f"⏳ <b>Slowmode Skipped:</b> {cycle.skipped_count}\n\n"
    )

    if failed_logs:
        text += "⚠️ <b>Failure Reasons (Sample Top 10):</b>\n"
        for log in failed_logs[:10]:
            err = log.error_reason or "Unknown Error"
            text += f"• <code>{log.group_identifier}</code>: <i>{err[:45]}</i>\n"
    else:
        text += "<i>No failures recorded for this cycle! All messages were delivered cleanly.</i>\n"

    kb = [
        [InlineKeyboardButton(text="⬅️ Back", callback_data=f"rpt_acc_{cycle.account_id}" if cycle.account_id else "sec_reports")]
    ]
    try:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("rpt_export_"))
async def cb_export_failures_txt(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass

    account_id = int(query.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        cycles = await get_recent_cycles(session, limit=10, account_id=account_id)
        all_failed = []
        for c in cycles:
            failed = await get_cycle_failed_logs(session, c.id)
            all_failed.extend(failed)

    if not all_failed:
        try:
            await query.answer("No broadcast failures recorded to export!", show_alert=True)
        except Exception:
            pass
        return

    content = f"BROADCAST FAILURE REPORT — Account #{account_id}\n" + "=" * 50 + "\n\n"
    for log in all_failed:
        content += f"{log.group_identifier} | Reason: {log.error_reason or 'N/A'} | Cycle #{log.cycle_id} | Sent: {log.sent_at}\n"

    file_bytes = io.BytesIO(content.encode("utf-8"))
    file_bytes.name = f"broadcast_failures_account_{account_id}.txt"
    input_file = BufferedInputFile(file_bytes.getvalue(), filename=file_bytes.name)

    await query.message.answer_document(
        document=input_file,
        caption=f"📄 Exported {len(all_failed)} broadcast failure entries."
    )


@router.callback_query(F.data.startswith("rpt_clean_"))
async def cb_clean_account_dead_links(query: CallbackQuery):
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
        await query.answer(f"🧹 Removed {res['deleted']} dead links! {res['active']} active groups remaining.", show_alert=True)
    except Exception:
        pass
    await cb_account_report_detail(query)
