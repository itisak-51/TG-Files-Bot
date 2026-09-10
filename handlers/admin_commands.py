"""
Direct-command fallbacks for admin setup. These exist because the
button-driven flow requires a "pending state" that's easy to lose (switching
menus, restarting the chat, etc.) — a plain command can't lose its context.
They also actively verify the bot can see/use the channel, instead of just
trusting whatever ID was typed.
"""
from telegram import Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db


def _parse_channel_id(raw: str):
    raw = raw.strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return None


async def setstorage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/setstorage -1001234567890</code>\n\n"
            "Tip: get the ID by adding <b>@userinfobot</b> to the channel, or forwarding "
            "any post from it there.",
            parse_mode="HTML",
        )
        return

    channel_id = _parse_channel_id(context.args[0])
    if channel_id is None:
        await update.message.reply_text("❌ That doesn't look like a numeric channel ID (e.g. -1001234567890).")
        return

    ok, detail = await _verify_bot_can_post(context, channel_id)
    if not ok:
        await update.message.reply_text(f"❌ Couldn't set storage channel:\n{detail}", parse_mode="HTML")
        return

    db.set_setting("storage_channel_id", str(channel_id))
    try:
        chat = await context.bot.get_chat(channel_id)
        invite_link = f"https://t.me/{chat.username}" if chat.username else await context.bot.export_chat_invite_link(channel_id)
        db.upsert_known_chat(channel_id, chat.title or str(channel_id), chat.type, True, invite_link)
    except Exception:
        pass  # already verified reachable above; caching into known_chats is a nice-to-have, not required
    await update.message.reply_text(
        f"✅ Storage channel set to <code>{channel_id}</code>! {detail}", parse_mode="HTML"
    )


async def checkstorage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diagnostic: reports exactly why the currently-configured storage channel
    would or wouldn't work, instead of leaving admins guessing."""
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    raw = db.get_setting("storage_channel_id")
    if not raw:
        await update.message.reply_text("⚠️ No storage channel is configured yet. Use /setstorage <id>.")
        return

    channel_id = int(raw)
    ok, detail = await _verify_bot_can_post(context, channel_id)
    icon = "✅" if ok else "❌"
    await update.message.reply_text(f"{icon} Storage channel <code>{channel_id}</code>:\n{detail}", parse_mode="HTML")


async def _verify_bot_can_post(context, channel_id: int):
    """Returns (ok: bool, human_readable_detail: str)."""
    try:
        chat = await context.bot.get_chat(channel_id)
    except BadRequest as e:
        return False, (
            f"Telegram says: <i>{e.message}</i>\n\n"
            "Most common cause: wrong ID. Channel IDs must include the <code>-100</code> prefix "
            "(e.g. <code>-1001234567890</code>, not <code>1234567890</code>)."
        )
    except Forbidden:
        return False, "The bot has never seen this chat — add it to the channel first."
    except Exception as e:
        return False, f"Unexpected error: <i>{e}</i>"

    try:
        member = await context.bot.get_chat_member(channel_id, context.bot.id)
    except Exception as e:
        return False, f"Found the chat (<b>{chat.title}</b>) but couldn't check the bot's membership: <i>{e}</i>"

    if member.status not in ("administrator", "creator"):
        return False, (
            f"Found the chat (<b>{chat.title}</b>) but the bot is only a <b>{member.status}</b> there, "
            "not an admin. Promote it to admin with at least \"Post Messages\" permission."
        )

    can_post = getattr(member, "can_post_messages", True)  # creator has no explicit flag, always True
    if can_post is False:
        return False, (
            f"The bot is an admin in <b>{chat.title}</b> but its \"Post Messages\" permission is off. "
            "Enable it in the channel's admin settings."
        )

    return True, f"Bot confirmed as admin in <b>{chat.title}</b> with post permission."
