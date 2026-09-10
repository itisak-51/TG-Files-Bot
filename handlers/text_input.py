from telegram import MessageOriginChannel, Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
import nav
import handlers.callbacks as screens
from handlers.callbacks import _settings_text, _users_hub_text, _admins_text, _forcesub_hub_text, _files_hub_text
from handlers.chat_tracking import verify_and_register_chat

ALL_BUTTON_LABELS = nav.all_button_labels()

DYNAMIC_ARRIVAL_TEXT = {
    "settings": _settings_text,
    "users": _users_hub_text,
    "admins": _admins_text,
    "forcesub": _forcesub_hub_text,
    "files": _files_hub_text,
}


def _forwarded_channel_id(message):
    """Telegram's Bot API 7.0+ replaced the old forward_from_chat field with
    forward_origin. Check the new field first, then fall back to the old one
    for older clients that might still populate it."""
    origin = getattr(message, "forward_origin", None)
    if isinstance(origin, MessageOriginChannel):
        return origin.chat.id
    if getattr(message, "forward_from_chat", None):
        return message.forward_from_chat.id
    return None


def _parsed_chat_id(message, text: str):
    channel_id = _forwarded_channel_id(message)
    if channel_id is not None:
        return channel_id
    if text.lstrip("-").isdigit():
        return int(text)
    return None


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        return  # regular users have no menu buttons and no pending admin states

    message = update.message
    text = (message.text or "").strip()

    # ---------------- Bottom reply-keyboard navigation ----------------
    if text in ALL_BUTTON_LABELS:
        context.user_data.pop("state", None)  # a nav tap always supersedes any pending prompt
        await _handle_menu_button(message, context, text)
        return

    state = context.user_data.get("state")
    if not state:
        if text.lstrip("-").isdigit() and len(text.lstrip("-")) >= 6:
            await message.reply_text(
                "ℹ️ That looks like a channel ID, but I'm not currently waiting for one.\n\n"
                "Open the relevant Settings screen first, *then* send the ID — or run /setstorage <id> directly."
            )
        return

    try:
        if state == "AWAITING_STORAGE":
            channel_id = _parsed_chat_id(message, text)
            if channel_id is None:
                await message.reply_text("❌ Forward a message from the channel, or send a numeric channel ID.")
                return
            ok, note = await verify_and_register_chat(context, channel_id)
            if not ok:
                await message.reply_text(note, parse_mode="HTML")
                return
            db.set_setting("storage_channel_id", str(channel_id))
            await message.reply_text(f"{note}\n\n✅ Storage channel set!", parse_mode="HTML")

        elif state == "AWAITING_WELCOME":
            db.set_text("welcome", text)
            await message.reply_text("✅ Welcome message updated!", reply_markup=kb.welcome_edit_kb())

        elif state == "AWAITING_AUTODELETE":
            if not text.isdigit():
                await message.reply_text("❌ Please send a whole number of seconds (0 disables auto-delete).")
                return
            db.set_setting("auto_delete_seconds", text)
            await message.reply_text(f"✅ Auto-delete timer set to <code>{text}s</code>!", parse_mode="HTML")

        elif state == "AWAITING_BROADCAST":
            ids = db.all_user_ids()
            await message.reply_text(f"⏳ Broadcasting to {len(ids)} users...")
            success = 0
            for uid in ids:
                try:
                    await message.copy(chat_id=uid)
                    success += 1
                except Exception:
                    pass
            await message.reply_text(f"✅ Message Broadcasted to {success}/{len(ids)} Users")

        elif state == "AWAITING_ADD_FORCESUB_MANUAL":
            channel_id = _parsed_chat_id(message, text)
            if channel_id is None:
                await message.reply_text("❌ Forward a message from the channel/group, or send its numeric ID.")
                return
            ok, note = await verify_and_register_chat(context, channel_id)
            if not ok:
                await message.reply_text(note, parse_mode="HTML")
                return
            chat = db.get_known_chat(channel_id)
            db.add_force_sub_channel(channel_id, chat[1] if chat else str(channel_id), chat[3] if chat else "")
            await message.reply_text(f"{note}\n\n✅ Added to Force-Sub!", parse_mode="HTML")

        elif state.startswith("AWAITING_EDIT_TEXT:"):
            key = state.split(":", 1)[1]
            db.set_text(key, message.text or "")
            await message.reply_text("✅ Text updated!")

        context.user_data.pop("state", None)

    except ValueError:
        await message.reply_text("❌ Invalid input. Please try again or send /cancel.")


async def _handle_menu_button(message, context: ContextTypes.DEFAULT_TYPE, label: str):
    level = context.user_data.get("level", "root")

    # "Back" always resolves relative to whatever level we're currently at
    if label == nav.BACK:
        parent = nav.LEVEL_PARENT.get(level, "root")
        context.user_data["level"] = parent
        builder = DYNAMIC_ARRIVAL_TEXT.get(parent)
        text = builder() if builder else nav.LEVEL_ARRIVAL_TEXT.get(parent, "🏠")
        await message.reply_text(text, reply_markup=nav.reply_kb(parent), parse_mode="HTML")
        return

    async def goto(new_level: str):
        context.user_data["level"] = new_level
        builder = DYNAMIC_ARRIVAL_TEXT.get(new_level)
        text = builder() if builder else nav.LEVEL_ARRIVAL_TEXT[new_level]
        await message.reply_text(text, reply_markup=nav.reply_kb(new_level), parse_mode="HTML")

    if level == "root":
        if label == "📤 Upload File":
            await message.reply_text(
                "📤 <b>Upload a File</b>\n\nSend me any document, video, photo, audio, voice note, GIF, or sticker "
                "right here. I'll secure it and hand you a shareable link!", parse_mode="HTML",
            )
        elif label == "🛠 Admin Panel":
            await goto("admin")
        elif label == "❓ Help":
            await message.reply_text(db.get_text("help"), parse_mode="HTML")
        elif label == "ℹ️ About":
            await message.reply_text(db.get_text("about"), parse_mode="HTML")

    elif level == "admin":
        if label == "📊 Statistics":
            await screens.screen_stats(message, context)
        elif label == "⚙️ Settings":
            await goto("settings")
        elif label == "👥 Users":
            await goto("users")
        elif label == "🛡 Admins":
            await goto("admins")
        elif label == "📢 Broadcast":
            await screens.screen_broadcast_prompt(message, context)
        elif label == "🗄 Files Management":
            await goto("files")
        elif label == "💾 Backup":
            await goto("backup")

    elif level == "settings":
        if label == "🔒 Storage Channel":
            await screens.screen_storage(message, context)
        elif label == "✍️ Welcome Message":
            await screens.screen_welcome_prompt(message, context)
        elif label == "⏱ Auto-Delete Timer":
            await screens.screen_autodelete_prompt(message, context)
        elif label == "🛡 Toggle Content Protection":
            await screens.do_toggle_protect(message, context)
        elif label == "🔐 Force Channel Subscription":
            await goto("forcesub")
        elif label == "🎛 Edit Mode":
            await screens.screen_edit_mode(message, context)

    elif level == "forcesub":
        if label == "📄 Show Channels":
            await screens.screen_fsub_show(message, context)
        elif label == "➕ Add Channels":
            await screens.screen_fsub_add_picker(message, context)
        elif label == "➖ Remove Channels":
            await screens.screen_fsub_remove_picker(message, context)

    elif level == "users":
        if label == "📋 List Users":
            await screens.screen_list_users(message, context)
        elif label == "🚫 Ban Users":
            await screens.screen_ban_picker(message, context)
        elif label == "✅ Unban Users":
            await screens.screen_unban_picker(message, context)
        elif label == "📥 Export Users List":
            await screens.do_export_users(message, context)

    elif level == "admins":
        if label == "➕ Add Admin":
            await screens.screen_add_admin_picker(message, context)
        elif label == "➖ Remove Admin":
            await screens.screen_remove_admin_picker(message, context)

    elif level == "files":
        if label == "🔗 Get Link":
            await screens.screen_files_getlink_picker(message, context)
        elif label == "🗑 Remove File":
            await screens.screen_files_remove_picker(message, context)
        elif label == "🆔 Change File ID":
            await screens.screen_files_changeid_picker(message, context)

    elif level == "backup":
        if label == "💾 Backup Data":
            await screens.do_backup(message, context)
        elif label == "♻️ Restore Data":
            await screens.screen_restore_prompt(message, context)
        elif label == "🔥 Destroy Data":
            await screens.screen_destroy_confirm(message, context)
