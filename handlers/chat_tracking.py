"""
Telegram's Bot API has no "list every chat I'm in" endpoint — the only two
ways to learn which groups/channels a bot administers are:

1. Passive: listen for my_chat_member updates (fired whenever the bot is
   added, removed, promoted, or demoted anywhere) and remember the result.
   This is instant but only fires for changes that happen *after* the bot
   started listening — so a chat where the bot was already admin before
   this feature existed will never send that event on its own.

2. Active: given a chat_id (from a forwarded message or manual entry),
   call get_chat_member(chat_id, bot_id) right then to check the *current*
   status live, and cache that. This is what fixes "detection isn't
   working" for channels/groups added before this feature was deployed —
   the very first time you point the bot at one (forward a message from
   it, or type its ID), it gets verified and permanently remembered from
   then on, refreshed live every time a channel-picker screen opens.

Both paths write into the same known_chats table, so once a chat is known
by either method it shows up in every "pick a channel" menu going forward.
"""
import logging

from telegram import Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)

ADMIN_STATUSES = ("administrator", "creator")
TRACKED_CHAT_TYPES = ("channel", "group", "supergroup")


async def _invite_link_for(context, chat) -> str:
    if chat.username:
        return f"https://t.me/{chat.username}"
    try:
        return await context.bot.export_chat_invite_link(chat.id)
    except Exception as e:
        logger.warning("Couldn't export invite link for %s: %s", chat.id, e)
        return ""


async def track_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passive path — driven by Telegram pushing us an event."""
    cmu = update.my_chat_member
    if cmu is None:
        return

    chat = cmu.chat
    if chat.type not in TRACKED_CHAT_TYPES:
        return

    new_status = cmu.new_chat_member.status
    is_admin_here = new_status in ADMIN_STATUSES
    invite_link = await _invite_link_for(context, chat) if is_admin_here else ""

    db.upsert_known_chat(chat.id, chat.title or str(chat.id), chat.type, is_admin_here, invite_link)
    logger.info(
        "Chat membership update: %s (%s) -> %s (admin=%s)",
        chat.title, chat.id, new_status, is_admin_here,
    )


async def verify_and_register_chat(context, chat_id: int) -> tuple:
    """Active path — call this the moment an admin gives us a chat_id by any
    means (forwarded message, typed ID). Checks the bot's *real, current*
    admin status right now via the API and caches it, regardless of whether
    a my_chat_member event ever fired for it.

    Returns (ok: bool, message: str) — message explains what happened, for
    showing straight back to the admin.
    """
    try:
        chat = await context.bot.get_chat(chat_id)
    except (BadRequest, Forbidden) as e:
        return False, f"❌ Couldn't find that chat: {e}"

    if chat.type not in TRACKED_CHAT_TYPES:
        return False, "❌ That's not a channel or group."

    try:
        member = await context.bot.get_chat_member(chat_id, context.bot.id)
        is_admin_here = member.status in ADMIN_STATUSES
    except (BadRequest, Forbidden) as e:
        return False, f"❌ Couldn't check my own membership there: {e}"

    if not is_admin_here:
        return False, f"⚠️ I'm in \"{chat.title}\" but I'm not an admin there yet — promote me first."

    invite_link = await _invite_link_for(context, chat)
    db.upsert_known_chat(chat.id, chat.title or str(chat.id), chat.type, True, invite_link)
    return True, f"✅ Verified — I'm an admin in \"{chat.title}\". It's now available in channel pickers."


async def refresh_all_known_chats(context) -> int:
    """Re-verifies every previously-known chat's admin status live (catches
    demotions/removals too, not just new promotions). Returns how many are
    currently admin-verified after the refresh."""
    admin_count = 0
    for chat_id in db.all_known_chat_ids():
        is_admin_here = False
        try:
            chat = await context.bot.get_chat(chat_id)
            member = await context.bot.get_chat_member(chat_id, context.bot.id)
            is_admin_here = member.status in ADMIN_STATUSES
            invite_link = await _invite_link_for(context, chat) if is_admin_here else ""
            db.upsert_known_chat(chat_id, chat.title or str(chat_id), chat.type, is_admin_here, invite_link)
        except (BadRequest, Forbidden):
            # Bot can no longer see this chat at all (kicked, chat deleted, etc.)
            db.upsert_known_chat(chat_id, str(chat_id), "unknown", False, "")
        except Exception as e:
            logger.warning("Refresh failed for %s: %s", chat_id, e)
            continue
        if is_admin_here:
            admin_count += 1
    return admin_count
