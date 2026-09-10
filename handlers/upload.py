import asyncio
import secrets

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb


def _detect_type(message) -> str:
    if message.document:
        return "document"
    if message.video:
        return "video"
    if message.photo:
        return "photo"
    if message.audio:
        return "audio"
    if message.animation:
        return "animation"
    if message.voice:
        return "voice"
    if message.video_note:
        return "video_note"
    if message.sticker:
        return "sticker"
    return "file"


def _display_name(message, file_type: str) -> str:
    """Best-effort human-readable filename for the Files Management list."""
    if message.document and message.document.file_name:
        return message.document.file_name
    if message.video and message.video.file_name:
        return message.video.file_name
    if message.audio:
        return message.audio.file_name or message.audio.title or f"Audio_{message.audio.file_unique_id[:6]}"
    if message.animation and message.animation.file_name:
        return message.animation.file_name

    unique = {
        "photo": message.photo[-1].file_unique_id if message.photo else "",
        "voice": message.voice.file_unique_id if message.voice else "",
        "video_note": message.video_note.file_unique_id if message.video_note else "",
        "sticker": message.sticker.file_unique_id if message.sticker else "",
        "video": message.video.file_unique_id if message.video else "",
        "document": message.document.file_unique_id if message.document else "",
        "animation": message.animation.file_unique_id if message.animation else "",
    }.get(file_type, "")
    label = file_type.replace("_", " ").title().replace(" ", "")
    return f"{label}_{unique[:6]}" if unique else label


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user

    if db.is_banned(user.id):
        await message.reply_text(db.get_text("banned_notice"), parse_mode="HTML")
        return

    db.track_user(user.id, user.first_name or "", user.username or "")

    # A document sent while "Restore Data" is pending is backup data, not a
    # file to store — hand it off instead of treating it as an upload.
    if context.user_data.get("state") == "AWAITING_RESTORE_FILE" and message.document:
        from handlers.backup_restore import handle_restore_upload
        await handle_restore_upload(update, context)
        return

    if not db.is_admin(user.id):
        await message.reply_text(db.get_text("upload_blocked"), parse_mode="HTML")
        return

    storage_channel_id = db.get_setting("storage_channel_id")
    if not storage_channel_id:
        await message.reply_text(
            "⚠️ The storage channel hasn't been configured yet. "
            "Open ⚙️ Settings → 🔒 Storage Channel to set it up."
        )
        return

    status_msg = await message.reply_text("⏳ <b>Processing...</b>\nSecuring your file...", parse_mode="HTML")

    try:
        file_type = _detect_type(message)
        file_name = _display_name(message, file_type)
        caption = message.caption or ""

        # copy_message (not forward) so the storage channel never reveals the
        # uploader's identity via a "Forwarded from" tag, and it works
        # regardless of the uploader's own forward-privacy settings. The
        # original caption (if any) is preserved automatically; if none was
        # sent, none is added.
        channel_msg = await context.bot.copy_message(
            chat_id=int(storage_channel_id),
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
        # Prefix with a short random token so file IDs aren't guessable purely from message order
        file_id = f"{channel_msg.message_id}{secrets.token_hex(2)}"
        db.add_file(file_id, channel_msg.message_id, user.id, file_type, file_name, caption)

        await status_msg.edit_text("✅ <b>Uploaded!</b>\nGenerating your link...", parse_mode="HTML")
        await asyncio.sleep(0.4)

        link = f"https://t.me/{context.bot.username}?start={file_id}"
        final_text = f"✅ <b>Stored Successfully!</b>\n\n🔗 <b>Your Link:</b>\n<code>{link}</code>"
        await status_msg.edit_text(final_text, reply_markup=kb.home_kb(), parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Error:</b> {e}", parse_mode="HTML")
