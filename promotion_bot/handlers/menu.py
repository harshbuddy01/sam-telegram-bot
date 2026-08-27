from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from database.crud import get_all_sender_accounts, get_group_stats_for_account
from core.broadcaster import broadcaster
import config

router = Router()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📱 Add Numbers", callback_data="sec_auth"),
            InlineKeyboardButton(text="👥 Group Joiner", callback_data="sec_joiner"),
        ],
        [
            InlineKeyboardButton(text="✏️ Message Setup", callback_data="sec_message"),
            InlineKeyboardButton(text="📊 Reports", callback_data="sec_reports"),
        ],
        [
            InlineKeyboardButton(text="🚀 Start / Stop", callback_data="sec_broadcast"),
            InlineKeyboardButton(text="⏰ Scheduler", callback_data="sec_scheduler"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_dashboard_text() -> str:
    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        stats_list = []
        for acc in accounts:
            st = await get_group_stats_for_account(session, acc.id)
            stats_list.append((acc, st))

    acc_count = len(accounts)
    workers_status = broadcaster.get_all_workers_status()
    running_workers = [w for w in workers_status if w.get("is_running")]
    running_count = len(running_workers)

    text = (
        "🤖 <b>SAM STORE AD BOT — CONTROL CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Connected Numbers ({acc_count}):</b>\n"
    )

    if not accounts:
        text += "<i>No phone numbers connected yet. Tap <b>📱 Add Numbers</b> to login.</i>\n"
    else:
        for acc, st in stats_list:
            status_icon = "🟢" if acc.status == "ACTIVE" else "🔴"
            user_label = f"@{acc.username}" if acc.username else (acc.first_name or "N/A")
            is_broadcasting = broadcaster.is_account_broadcasting(acc.id)
            bc_state = " [🚀 BROADCASTING]" if is_broadcasting else ""
            text += (
                f"{status_icon} <b>{acc.phone}</b> ({user_label}){bc_state}\n"
                f"   └ 🎯 <b>Groups:</b> {st['ACTIVE']} active / {st['TOTAL']} total\n"
            )

    text += (
        f"\n⚙️ <b>Live Status:</b>\n"
        f"• Active Workers: <code>{running_count}/{acc_count}</code>\n"
        f"• Anti-Ban Engine: <code>ACTIVE (Spintax + Jitter)</code>\n\n"
        "👇 <i>Select a section below to get started:</i>"
    )
    return text


@router.message(Command("start", "menu", "admin"))
async def cmd_main_menu(message: Message, state: FSMContext = None):
    if not config.is_admin(message.from_user.id):
        return
    if state:
        await state.clear()
    text = await build_dashboard_text()
    await message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(query: CallbackQuery, state: FSMContext = None):
    if not config.is_admin(query.from_user.id):
        return
    try:
        await query.answer()
    except Exception:
        pass
    if state:
        await state.clear()
    text = await build_dashboard_text()
    try:
        await query.message.edit_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    except Exception:
        await query.message.answer(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
