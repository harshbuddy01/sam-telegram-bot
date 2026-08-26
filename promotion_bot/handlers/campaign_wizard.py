import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import AsyncSessionLocal
from database.crud import (
    get_all_sender_accounts,
    get_active_sender_account,
    set_active_sender_account,
    get_active_promo_message,
    update_promo_message,
    get_group_stats,
    get_setting,
    set_setting
)
from core.client import tg_manager
from core.broadcaster import broadcaster
from utils.spintax import prepare_broadcast_message
from utils.premium_emojis import parse_shortcodes_to_tg_emoji
import config

router = Router(name="campaign_wizard")

class WizardStates(StatesGroup):
    editing_message_text = State()

# ==================== STEP 1: CHOOSE / SWITCH SENDER NUMBER ====================

async def render_step1_account_selection(query: CallbackQuery | Message):
    async with AsyncSessionLocal() as session:
        accounts = await get_all_sender_accounts(session)
        active_acc = await get_active_sender_account(session)

    kb = []
    for acc in accounts:
        mark = "✅ [SELECTED]" if acc.is_active else "⚪"
        prem = "👑" if acc.is_premium else ""
        btn_text = f"{mark} {acc.phone} {prem} (@{acc.username or acc.first_name or 'User'})"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"wiz_acc_{acc.id}")])

    kb.append([InlineKeyboardButton(text="➕ Add Another Number", callback_data="auth_start_login")])
    
    if active_acc:
        kb.append([InlineKeyboardButton(text="➡️ Next: Promo Message", callback_data="wiz_step2")])
    kb.append([InlineKeyboardButton(text="❌ Cancel Wizard", callback_data="main_menu")])

    sender_status = f"<code>{active_acc.phone}</code>" if active_acc else "<i>None selected (Please add or select a number)</i>"

    text = (
        "🚀 <b>CAMPAIGN WIZARD — STEP 1 OF 4: SENDER NUMBER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Current Selected Number:</b> {sender_status}\n\n"
        "Select which phone number / Telegram account should send this promotion cycle, or add a new number:\n"
    )
    
    if isinstance(query, CallbackQuery):
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        await query.answer()
    else:
        await query.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.message(Command("wizard"))
async def cmd_wizard(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    await render_step1_account_selection(message)

@router.callback_query(F.data == "start_wizard")
async def cb_start_wizard(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()
    await render_step1_account_selection(query)

@router.callback_query(F.data.startswith("wiz_acc_"))
async def cb_wizard_select_account(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    acc_id = int(query.data.replace("wiz_acc_", ""))
    async with AsyncSessionLocal() as session:
        acc = await set_active_sender_account(session, acc_id)
        
    if acc:
        await tg_manager.switch_to_account(acc.session_string, acc.id, acc.phone)
        await query.answer(f"Selected {acc.phone} for this campaign!")
    await render_step1_account_selection(query)

# ==================== STEP 2: PROMO MESSAGE ====================

@router.callback_query(F.data == "wiz_step2")
async def cb_wizard_step2(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()

    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)

    kb = [
        [
            InlineKeyboardButton(text="✏️ Edit Promo Text", callback_data="wiz_edit_text"),
            InlineKeyboardButton(text="🖼️ Set Media (Photo/Video)", callback_data="promo_set_media")
        ],
        [
            InlineKeyboardButton(text="👀 Live Preview", callback_data="promo_preview")
        ],
        [
            InlineKeyboardButton(text="⬅️ Back (Step 1)", callback_data="start_wizard"),
            InlineKeyboardButton(text="➡️ Next: Target Groups", callback_data="wiz_step3")
        ]
    ]

    text = (
        "🚀 <b>CAMPAIGN WIZARD — STEP 2 OF 4: PROMO MESSAGE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Current Promo Message for this Campaign:</b>\n"
        "────────────────────────────\n"
        f"{promo.text}\n"
        "────────────────────────────\n"
        f"<b>Attached Media:</b> <code>{promo.media_type.upper()}</code>\n\n"
        "<i>You can keep this message, edit it with Premium emojis, or attach media before proceeding.</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), disable_web_page_preview=True)
    await query.answer()

@router.callback_query(F.data == "wiz_edit_text")
async def cb_wizard_edit_text(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.set_state(WizardStates.editing_message_text)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="wiz_step2")]
    ])
    await query.message.edit_text(
        "✏️ <b>Enter Promotion Message:</b>\n\n"
        "Send the promotion message text you want to broadcast.\n"
        "Supports HTML, Spintax <code>{A|B}</code>, and shortcodes like <code>:crown:</code>, <code>:fire:</code>, <code>:star:</code>:\n\n"
        "<i>Send text now:</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await query.answer()

@router.message(WizardStates.editing_message_text)
async def handle_wizard_text(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    new_text = message.text or message.caption
    if not new_text:
        await message.answer("⚠️ Please send text content.")
        return

    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)
        await update_promo_message(session, new_text, media_type=promo.media_type, media_file_id=promo.media_file_id, media_path=promo.media_path)

    await state.clear()
    await message.answer("✅ <b>Promotion message updated!</b>", parse_mode="HTML")
    
    # Return to step 2
    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)
    kb = [
        [
            InlineKeyboardButton(text="✏️ Edit Text", callback_data="wiz_edit_text"),
            InlineKeyboardButton(text="🖼️ Set Media", callback_data="promo_set_media")
        ],
        [
            InlineKeyboardButton(text="👀 Live Preview", callback_data="promo_preview")
        ],
        [
            InlineKeyboardButton(text="⬅️ Back (Step 1)", callback_data="start_wizard"),
            InlineKeyboardButton(text="➡️ Next: Target Groups", callback_data="wiz_step3")
        ]
    ]
    text = (
        "🚀 <b>CAMPAIGN WIZARD — STEP 2 OF 4: PROMO MESSAGE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Updated Promo Message:</b>\n"
        "────────────────────────────\n"
        f"{promo.text}\n"
        "────────────────────────────"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), disable_web_page_preview=True)

# ==================== STEP 3: TARGET GROUPS ====================

@router.callback_query(F.data == "wiz_step3")
async def cb_wizard_step3(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()

    async with AsyncSessionLocal() as session:
        stats = await get_group_stats(session)

    kb = [
        [
            InlineKeyboardButton(text="➕ Add More Groups (Bulk Paste)", callback_data="groups_add_bulk"),
            InlineKeyboardButton(text="⚡ Run Auto-Joiner", callback_data="groups_auto_join")
        ],
        [
            InlineKeyboardButton(text="⬅️ Back (Step 2)", callback_data="wiz_step2"),
            InlineKeyboardButton(text="➡️ Next: Review & Launch", callback_data="wiz_step4")
        ]
    ]

    text = (
        "🚀 <b>CAMPAIGN WIZARD — STEP 3 OF 4: TARGET GROUPS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Total Saved Groups in Bot:</b> <code>{stats.get('TOTAL', 0)}</code>\n"
        f"• 🟢 Active & Ready: <code>{stats.get('ACTIVE', 0)}</code>\n"
        f"• ⏳ Slowmode Queued: <code>{stats.get('SLOWMODE', 0)}</code>\n"
        f"• 🔴 Banned / Inactive: <code>{stats.get('BANNED', 0) + stats.get('RESTRICTED', 0)}</code>\n\n"
        "✨ <b>No Repeated Work Needed:</b>\n"
        "All groups you previously added are saved permanently in the database! You do <b>NOT</b> need to re-add them every time.\n\n"
        "<i>If you have fresh groups to include, tap 'Add More Groups', or proceed to Step 4.</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await query.answer()

# ==================== STEP 4: REVIEW & LAUNCH ====================

@router.callback_query(F.data == "wiz_step4")
async def cb_wizard_step4(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()

    async with AsyncSessionLocal() as session:
        active_acc = await get_active_sender_account(session)
        promo = await get_active_promo_message(session)
        stats = await get_group_stats(session)
        interval = await get_setting(session, "interval_hours", str(config.DEFAULT_INTERVAL_HOURS))

    sender_label = f"{active_acc.phone} (@{active_acc.username or active_acc.first_name})" if active_acc else "❌ None"

    kb = [
        [
            InlineKeyboardButton(text="🚀 START BROADCAST CAMPAIGN NOW", callback_data="wiz_launch_now")
        ],
        [
            InlineKeyboardButton(text="⏱️ Repeat: 1h", callback_data="bc_set_interval_1"),
            InlineKeyboardButton(text="⏱️ Repeat: 2h", callback_data="bc_set_interval_2"),
            InlineKeyboardButton(text="⏱️ Repeat: 4h", callback_data="bc_set_interval_4")
        ],
        [
            InlineKeyboardButton(text="⬅️ Back (Step 3)", callback_data="wiz_step3"),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")
        ]
    ]

    text = (
        "🚀 <b>CAMPAIGN WIZARD — STEP 4 OF 4: REVIEW & LAUNCH</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📋 <b>Campaign Configuration Summary:</b>\n"
        f"• 📱 <b>Sender Account:</b> <code>{sender_label}</code>\n"
        f"• 📝 <b>Promo Content:</b> <code>Ready ({promo.media_type.upper()})</code>\n"
        f"• 👥 <b>Target Audience:</b> <code>{stats.get('ACTIVE', 0)} Active Groups</code>\n"
        f"• ⏱️ <b>Repeating Cycle:</b> <code>Every {interval} Hours</code>\n"
        f"• 🛡️ <b>Anti-Ban Math:</b> <code>18–35s Jitter + 4m Batch Pause</code>\n\n"
        "<b>Ready to launch? Tap the button below to start:</b>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await query.answer()

@router.callback_query(F.data == "wiz_launch_now")
async def cb_wizard_launch_now(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return

    if broadcaster.is_broadcasting:
        await query.answer("Broadcast is already actively running!", show_alert=True)
        return

    # Enable auto-repeating in settings
    async with AsyncSessionLocal() as session:
        await set_setting(session, "broadcast_enabled", "true")

    await query.answer("🚀 Launching Campaign!", show_alert=True)
    asyncio.create_task(broadcaster.execute_broadcast_round(trigger_type="CAMPAIGN_WIZARD"))

    await query.message.answer(
        "🎉 <b>CAMPAIGN ACTIVATED & RUNNING!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "The bot has started broadcasting to your target groups.\n"
        "You will receive real-time progress and a full summary report once completed or if you stop the round.\n\n"
        "<i>Use /menu to monitor live progress or pause at any time.</i>",
        parse_mode="HTML"
    )
