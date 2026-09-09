from telegram import MessageOriginChannel, Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb


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


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        return

    message = update.message
    state = context.user_data.get("state")

    if not state:
        # Don't fail silently on a stray ID — it's the #1 source of "nothing happened"
        # confusion. Nudge admins toward the right button instead of ignoring them.
        text = (message.text or "").strip()
        if text.lstrip("-").isdigit() and len(text.lstrip("-")) >= 6:
            await message.reply_text(
                "ℹ️ That looks like a channel ID, but I'm not currently waiting for one.\n\n"
                "Open /admin → ⚙️ Settings → 🔒 Storage Channel (or 🔐 Force Channel Subscription) "
                "first, *then* send the ID — or just run /setstorage <id> directly.",
            )
        return

    text = (message.text or "").strip()

    try:
        if state == "AWAITING_STORAGE":
            channel_id = _forwarded_channel_id(message)
            if channel_id is None:
                if text.lstrip("-").isdigit():
                    channel_id = int(text)
                else:
                    await message.reply_text("❌ Forward a message from the channel, or send a numeric channel ID.")
                    return
            db.set_setting("storage_channel_id", str(channel_id))
            await message.reply_text(f"✅ Storage channel set to <code>{channel_id}</code>!", parse_mode="HTML")

        elif state == "AWAITING_WELCOME":
            db.set_setting("welcome_msg", text)
            await message.reply_text("✅ Welcome message updated!", parse_mode="HTML",
                                      reply_markup=kb.welcome_edit_kb())

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
            await message.reply_text(
                f"✅ Message Broadcasted to {success}/{len(ids)} Users",
                reply_markup=kb.admin_main_kb(),
            )

        elif state == "AWAITING_ADD_FORCESUB_MANUAL":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 1 or not parts[0].lstrip("-").isdigit():
                await message.reply_text(
                    "❌ Invalid format. Use:\n<code>channel_id | Title | invite_link</code>", parse_mode="HTML"
                )
                return
            channel_id = int(parts[0])
            title = parts[1] if len(parts) > 1 else ""
            link = parts[2] if len(parts) > 2 else ""
            db.add_force_sub_channel(channel_id, title, link)
            await message.reply_text(f"✅ Force-Sub channel <code>{channel_id}</code> added!", parse_mode="HTML")

        context.user_data.pop("state", None)

    except ValueError:
        await message.reply_text("❌ Invalid input. Please try again or send /cancel.")
