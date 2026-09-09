"""
Telegram's Bot API has no "list every chat I'm in" endpoint — the only way
to know which groups/channels a bot administers is to listen for
my_chat_member updates (fired whenever the bot is added, removed, promoted,
or demoted anywhere) and remember the result ourselves.

This is what powers the "pick a channel" menus in the admin panel (Storage
Channel, Force-Sub Channels) instead of forcing admins to hunt down and
paste raw chat IDs by hand.

Caveat worth knowing: if the bot was already an admin in a chat *before*
this tracking existed (or before this update was deployed), Telegram won't
resend that event. Removing and re-adding the bot (or promoting/demoting it
once) re-triggers it. The manual "enter ID / forward a message" fallback in
Settings still exists for that edge case.
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)

ADMIN_STATUSES = ("administrator", "creator")
TRACKED_CHAT_TYPES = ("channel", "group", "supergroup")


async def track_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmu = update.my_chat_member
    if cmu is None:
        return

    chat = cmu.chat
    if chat.type not in TRACKED_CHAT_TYPES:
        return

    new_status = cmu.new_chat_member.status
    is_admin_here = new_status in ADMIN_STATUSES

    invite_link = ""
    if chat.username:
        invite_link = f"https://t.me/{chat.username}"
    elif is_admin_here:
        try:
            invite_link = await context.bot.export_chat_invite_link(chat.id)
        except Exception as e:
            logger.warning("Couldn't export invite link for %s: %s", chat.id, e)

    db.upsert_known_chat(chat.id, chat.title or str(chat.id), chat.type, is_admin_here, invite_link)
    logger.info(
        "Chat membership update: %s (%s) -> %s (admin=%s)",
        chat.title, chat.id, new_status, is_admin_here,
    )
