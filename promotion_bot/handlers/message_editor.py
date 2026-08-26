import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import AsyncSessionLocal
from database.crud import get_active_promo_message, update_promo_message
from utils.spintax import prepare_broadcast_message
from utils.premium_emojis import parse_shortcodes_to_tg_emoji, EMOJI_SHORTCODES
import config

router = Router(name="message_editor")

class PromoEditorStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()

def get_message_editor_keyboard(media_type: str = "none") -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="✏️ Edit Promo Text", callback_data="promo_edit_text"),
            InlineKeyboardButton(text="🖼️ Set Photo / Video", callback_data="promo_set_media")
        ],
        [
            InlineKeyboardButton(text="👀 Live Preview (How Groups See It)", callback_data="promo_preview")
        ],
        [
            InlineKeyboardButton(text="✨ Premium Emoji Guide", callback_data="promo_emoji_help"),
            InlineKeyboardButton(text="🌀 Spintax Guide", callback_data="promo_spintax_help")
        ]
    ]
    if media_type != "none":
        kb.append([InlineKeyboardButton(text="🗑️ Remove Media Attachment", callback_data="promo_remove_media")])
    kb.append([InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "menu_promo_msg")
async def cb_promo_menu(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.clear()
    
    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)

    text = (
        "📝 <b>PROMOTION MESSAGE MANAGER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Media Attachment:</b> <code>{promo.media_type.upper()}</code>\n\n"
        "<b>Current Promo Message Text:</b>\n"
        "────────────────────────────\n"
        f"{promo.text}\n"
        "────────────────────────────\n\n"
        "💡 <i>Tip: You can use HTML tags (<b>bold</b>, <i>italic</i>, <code>code</code>), Spintax {A|B|C}, and Premium custom emojis!</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_message_editor_keyboard(promo.media_type), disable_web_page_preview=True)
    await query.answer()

@router.callback_query(F.data == "promo_edit_text")
async def cb_edit_text_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.set_state(PromoEditorStates.waiting_for_text)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_promo_msg")]
    ])
    
    text = (
        "✏️ <b>Enter New Promotion Text:</b>\n\n"
        "Send the new text you want the bot to broadcast to all 300-400 groups.\n\n"
        "<b>Supported Features:</b>\n"
        "• Standard HTML tags: <code>&lt;b&gt;bold&lt;/b&gt;</code>, <code>&lt;i&gt;italic&lt;/i&gt;</code>\n"
        "• Spintax: <code>{🔥 Special Offer | ⚡ Flash Sale | 💎 Limited Discount}</code>\n"
        "• Custom Emoji Shortcodes: <code>:crown:</code>, <code>:fire:</code>, <code>:star:</code>, <code>:netflix:</code>, <code>:diamond:</code>\n"
        "• Direct Custom Emoji: <code>&lt;tg-emoji emoji-id=\"5447410659077661506\"&gt;👑&lt;/tg-emoji&gt;</code>\n\n"
        "<i>Send your text now:</i>"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb)
    await query.answer()

@router.message(PromoEditorStates.waiting_for_text)
async def handle_new_promo_text(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    
    new_text = message.text or message.caption
    if not new_text:
        await message.answer("⚠️ Please send text content for the promotion message.")
        return

    # Check for HTML formatting validity
    parsed_test = parse_shortcodes_to_tg_emoji(new_text)
    try:
        # Test parse in Telegram
        test_msg = await message.answer(f"✅ <i>Validating text formatting...</i>\n\n{parsed_test}", parse_mode="HTML")
        await test_msg.delete()
    except Exception as e:
        await message.answer(f"❌ <b>HTML Syntax Error:</b> {e}\nPlease check unclosed tags and send again.")
        return

    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)
        await update_promo_message(session, new_text, media_type=promo.media_type, media_file_id=promo.media_file_id, media_path=promo.media_path)

    await state.clear()
    await message.answer("🎉 <b>Promotion text updated successfully!</b>", parse_mode="HTML")
    
    # Return to menu
    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)
    dash_text = (
        "📝 <b>PROMOTION MESSAGE MANAGER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Media Attachment:</b> <code>{promo.media_type.upper()}</code>\n\n"
        "<b>Current Promo Message Text:</b>\n"
        "────────────────────────────\n"
        f"{promo.text}\n"
        "────────────────────────────"
    )
    await message.answer(dash_text, parse_mode="HTML", reply_markup=get_message_editor_keyboard(promo.media_type), disable_web_page_preview=True)

@router.callback_query(F.data == "promo_set_media")
async def cb_set_media_start(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    await state.set_state(PromoEditorStates.waiting_for_media)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_promo_msg")]
    ])
    
    text = (
        "🖼️ <b>Attach Media to Promotion:</b>\n\n"
        "Please send a <b>Photo</b> or <b>Video</b> in this chat.\n"
        "The bot will download and save it to broadcast alongside your promotion text to all groups."
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb)
    await query.answer()

@router.message(PromoEditorStates.waiting_for_media)
async def handle_new_promo_media(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return

    os.makedirs("media_storage", exist_ok=True)
    
    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_path = f"media_storage/promo_photo_{photo.file_unique_id}.jpg"
        
        bot_file = await message.bot.get_file(file_id)
        await message.bot.download_file(bot_file.file_path, file_path)
        
        async with AsyncSessionLocal() as session:
            promo = await get_active_promo_message(session)
            await update_promo_message(session, promo.text, media_type="photo", media_file_id=file_id, media_path=file_path)
            
        await state.clear()
        await message.answer("✅ <b>Promotion Photo saved successfully!</b>", parse_mode="HTML")
        
    elif message.video:
        video = message.video
        file_id = video.file_id
        file_path = f"media_storage/promo_video_{video.file_unique_id}.mp4"
        
        bot_file = await message.bot.get_file(file_id)
        await message.bot.download_file(bot_file.file_path, file_path)
        
        async with AsyncSessionLocal() as session:
            promo = await get_active_promo_message(session)
            await update_promo_message(session, promo.text, media_type="video", media_file_id=file_id, media_path=file_path)
            
        await state.clear()
        await message.answer("✅ <b>Promotion Video saved successfully!</b>", parse_mode="HTML")
    else:
        await message.answer("⚠️ Please send a Photo or Video file.")
        return

    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)
    dash_text = (
        "📝 <b>PROMOTION MESSAGE MANAGER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Media Attachment:</b> <code>{promo.media_type.upper()}</code>\n\n"
        "<b>Current Promo Message Text:</b>\n"
        "────────────────────────────\n"
        f"{promo.text}\n"
        "────────────────────────────"
    )
    await message.answer(dash_text, parse_mode="HTML", reply_markup=get_message_editor_keyboard(promo.media_type), disable_web_page_preview=True)

@router.callback_query(F.data == "promo_remove_media")
async def cb_remove_media(query: CallbackQuery, state: FSMContext):
    if not config.is_admin(query.from_user.id):
        return
    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)
        await update_promo_message(session, promo.text, media_type="none", media_file_id=None, media_path=None)
        promo = await get_active_promo_message(session)

    text = (
        "📝 <b>PROMOTION MESSAGE MANAGER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Media Attachment:</b> <code>NONE</code>\n\n"
        "<b>Current Promo Message Text:</b>\n"
        "────────────────────────────\n"
        f"{promo.text}\n"
        "────────────────────────────"
    )
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=get_message_editor_keyboard("none"), disable_web_page_preview=True)
    await query.answer("Media attachment removed!")

@router.callback_query(F.data == "promo_preview")
async def cb_promo_preview(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    
    async with AsyncSessionLocal() as session:
        promo = await get_active_promo_message(session)

    # Generate a live preview with Spintax resolution & emoji formatting
    sample_text = prepare_broadcast_message(promo.text, apply_spintax=True, apply_jitter=False)
    sample_text = parse_shortcodes_to_tg_emoji(sample_text)

    await query.message.answer("👀 <b>[LIVE PREVIEW — TARGET GROUP PERSPECTIVE]</b>", parse_mode="HTML")
    
    try:
        if promo.media_type == "photo" and promo.media_file_id:
            await query.message.answer_photo(photo=promo.media_file_id, caption=sample_text, parse_mode="HTML")
        elif promo.media_type == "video" and promo.media_file_id:
            await query.message.answer_video(video=promo.media_file_id, caption=sample_text, parse_mode="HTML")
        else:
            await query.message.answer(sample_text, parse_mode="HTML", disable_web_page_preview=False)
    except Exception as e:
        await query.message.answer(f"❌ Preview render error: {e}")

    await query.answer("Preview sent below!")

@router.callback_query(F.data == "promo_emoji_help")
async def cb_emoji_help(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    
    shortcuts = "\n".join([f"• <code>{code}</code> → {fallback}" for code, (doc_id, fallback) in EMOJI_SHORTCODES.items()])
    
    text = (
        "✨ <b>TELEGRAM PREMIUM CUSTOM EMOJIS GUIDE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "You can use any of these convenient shortcodes in your promo text:\n\n"
        f"{shortcuts}\n\n"
        "<b>Direct Custom Emoji HTML Syntax:</b>\n"
        "<code>&lt;tg-emoji emoji-id=\"5447410659077661506\"&gt;👑&lt;/tg-emoji&gt;</code>\n\n"
        "<i>When sent from your Telegram Premium Sender Account, these emojis render as authentic animated stickers!</i>"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Promo Manager", callback_data="menu_promo_msg")]
    ])
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb)
    await query.answer()

@router.callback_query(F.data == "promo_spintax_help")
async def cb_spintax_help(query: CallbackQuery):
    if not config.is_admin(query.from_user.id):
        return
    
    text = (
        "🌀 <b>ANTI-BAN SPINTAX GUIDE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>What is Spintax?</b>\n"
        "Spintax allows you to specify multiple text variations. The bot picks one randomly for every group so Telegram's spam filter sees unique messages.\n\n"
        "<b>Example Syntax:</b>\n"
        "<code>{🔥 Huge Sale | ⚡ Exclusive Discount | 💎 Flash Promo}</code>\n"
        "<code>Get your {Netflix | Prime | Spotify} account {now | today | instantly}!</code>\n\n"
        "<b>Nested Spintax Example:</b>\n"
        "<code>{Hello|Hi|Hey} {friend|buddy}, check {out this | our new} store!</code>"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back to Promo Manager", callback_data="menu_promo_msg")]
    ])
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb)
    await query.answer()
