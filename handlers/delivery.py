"""
Everything to do with: checking force-subscribe status, delivering a stored
file to a user, and running the live auto-delete countdown afterwards.

Deep-link delivery is intentionally minimal: a status message, then the
file (with its original caption, untouched), then a separate timer message.
Nothing else gets attached to that flow.
"""
import asyncio
import logging

from telegram.error import BadRequest, Forbidden

import database as db
import keyboards as kb

logger = logging.getLogger(__name__)


async def is_user_subscribed(context, user_id: int) -> bool:
    """True only if the user is a member of every configured force-sub channel.
    If no channels are configured, everyone passes."""
    channels = db.list_force_sub_channels()
    if not channels:
        return True

    for channel_id, _title, _link in channels:
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logger.warning("Sub check failed for channel %s / user %s: %s", channel_id, user_id, e)
            return False
    return True


async def prompt_join(update_or_query, file_id: str, is_callback: bool):
    channels = db.list_force_sub_channels()
    text = (
        "⚠️ <b>Subscription Required</b>\n\n"
        "Please join the channel(s)/group(s) below, then tap <b>Check Again</b> to unlock this file."
    )
    markup = kb.force_sub_kb(channels, file_id)
    if is_callback:
        await update_or_query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await update_or_query.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def deliver_file(context, chat_target, user_id: int, file_id: str, edit_status: bool):
    """chat_target: a callback_query (edit_status=True) or a Message (edit_status=False)."""
    row = db.get_file(file_id)
    if not row:
        text = "❌ File not found or was removed by an admin."
        if edit_status:
            await chat_target.edit_message_text(text)
        else:
            await chat_target.reply_text(text)
        return

    _fid, channel_msg_id, _uploader, _ftype, _fname, _caption, _uploaded_at = row
    storage_channel_id = db.get_setting("storage_channel_id")
    if not storage_channel_id:
        text = "❌ Storage channel is not configured yet. Ask an admin to set it up."
        if edit_status:
            await chat_target.edit_message_text(text)
        else:
            await chat_target.reply_text(text)
        return

    status_text = "⏳ <b>Fetching your file from the secure vault...</b>"
    if edit_status:
        status_msg = await chat_target.edit_message_text(status_text, parse_mode="HTML")
        status_msg_id = chat_target.message.message_id
    else:
        status_msg = await chat_target.reply_text(status_text, parse_mode="HTML")
        status_msg_id = status_msg.message_id

    protect = db.get_setting("protect_content", "0") == "1"

    try:
        # copy_message (not forward) so the delivered file carries its
        # original caption but no "forwarded from" trail, and works
        # regardless of the uploader's forward-privacy settings.
        sent_file = await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=int(storage_channel_id),
            message_id=channel_msg_id,
            protect_content=protect,
        )
    except (BadRequest, Forbidden) as e:
        logger.error("Delivery failed for file %s to user %s: %s", file_id, user_id, e)
        fail_text = "❌ Couldn't deliver the file. Please contact an admin."
        await context.bot.edit_message_text(chat_id=user_id, message_id=status_msg_id, text=fail_text)
        return

    auto_delete_seconds = int(db.get_setting("auto_delete_seconds", "300") or 0)

    if auto_delete_seconds > 0:
        timer_msg = await context.bot.send_message(
            user_id,
            f"⏳ <b>{auto_delete_seconds}s</b> remaining\n\n"
            "⚠️ <b>Do not forward this file anywhere else.</b> "
            "It will auto-delete for copyright protection — save it now.",
            parse_mode="HTML",
        )
        success_text = "✅ <b>Success!</b> Your file is above.\n⏳ Auto-delete timer started."
    else:
        timer_msg = None
        success_text = "✅ <b>Success!</b> Your file is above."

    await context.bot.edit_message_text(
        chat_id=user_id, message_id=status_msg_id, text=success_text,
        reply_markup=kb.home_kb(), parse_mode="HTML",
    )

    if timer_msg:
        asyncio.create_task(
            run_countdown(context, user_id, timer_msg.message_id, sent_file.message_id, auto_delete_seconds)
        )


async def run_countdown(context, chat_id: int, timer_msg_id: int, file_msg_id: int, total_seconds: int):
    bar_length = 20
    # Update roughly once per second, but cap update frequency for very long timers
    step = max(1, total_seconds // 60)

    for seconds_left in range(total_seconds, 0, -step):
        emoji = "⏳" if seconds_left > total_seconds * 0.3 else ("⚠️" if seconds_left > total_seconds * 0.1 else "🔴")
        filled = int((seconds_left / total_seconds) * bar_length)
        filled = max(0, min(bar_length, filled))
        bar = "█" * filled + "░" * (bar_length - filled)
        text = f"{emoji} | {bar} <b>{seconds_left}s</b>\n\n⚠️ <i>Do not forward this file anywhere else.</i>"
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=timer_msg_id, text=text, parse_mode="HTML")
        except Exception:
            pass
        await asyncio.sleep(step)

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=file_msg_id)
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=timer_msg_id,
            text="🗑 <b>Deleted</b>\n\nThe file was removed for copyright protection.",
            parse_mode="HTML",
        )
    except Exception:
        pass
