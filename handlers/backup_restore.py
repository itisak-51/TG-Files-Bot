"""
Handles the "send me the .db file" half of Restore Data. Split out from
upload.py so a restore-in-progress document doesn't get mixed up with the
normal file-store upload path.
"""
import os

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import nav


async def handle_restore_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    context.user_data.pop("state", None)

    status = await message.reply_text("⏳ Downloading backup file...")
    tmp_path = f"/tmp/restore_{user.id}_{message.document.file_unique_id}.db"

    try:
        tg_file = await message.document.get_file()
        await tg_file.download_to_drive(tmp_path)

        if not db.is_valid_backup_file(tmp_path):
            await status.edit_text(
                "❌ That doesn't look like a valid backup from this bot (missing expected tables). "
                "Nothing was changed."
            )
            return

        await status.edit_text("⏳ Restoring... the bot will pick up exactly where that backup left off.")
        ok = db.restore_from(tmp_path)
        if ok:
            await status.edit_text(
                "✅ <b>Restore complete!</b>\n\nAll users, admins, files, and settings are back exactly as they "
                "were in that backup.", parse_mode="HTML",
            )
            context.user_data["level"] = "backup"
            await message.reply_text(
                nav.LEVEL_ARRIVAL_TEXT["backup"], reply_markup=nav.reply_kb("backup"), parse_mode="HTML"
            )
        else:
            await status.edit_text("❌ Restore failed validation. Nothing was changed.")
    except Exception as e:
        await status.edit_text(f"❌ Restore failed: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
