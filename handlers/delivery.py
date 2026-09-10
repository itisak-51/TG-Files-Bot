"""
Everything to do with: checking force-subscribe status (showing only the
channels a user still hasn't joined — never the full list once some are
already done), delivering a stored file, and running the live auto-delete
countdown afterwards.

Deep-link delivery is intentionally minimal: a status message, then the
file (with its original caption, untouched unless a brand label is set),
then a separate timer message. Nothing else gets attached to that flow.
Subscription is re-checked from scratch every single time — nothing about
a past pass is ever cached, so a user who leaves a channel later is caught
again next time.
"""
import asyncio
import logging

from telegram.error import BadRequest, Forbidden

import database as db
import keyboards as kb

logger = logging.getLogger(__name__)


async def get_unjoined_channels(context, user_id: int) -> list:
    """Live-checks membership against every configured force-sub channel and
    returns only the ones the user hasn't joined. Empty list = fully
    subscribed. Never cached — always a fresh check."""
    channels = db.list_force_sub_channels()
    unjoined = []
    for channel_id, title, link in channels:
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status in ("left", "kicked"):
                unjoined.append((channel_id, title, link))
        except Exception as e:
            logger.warning("Sub check failed for channel %s / user %s: %s", channel_id, user_id, e)
            unjoined.append((channel_id, title, link))
    return unjoined


async def is_user_subscribed(context, user_id: int) -> bool:
    return not await get_unjoined_channels(context, user_id)


async def prompt_join(target, unjoined_channels: list, continue_data: str, is_callback: bool):
    """Shows ONLY the channels still not joined — if the admin has 2
    channels configured and the user joined 1, only the remaining 1 is
    shown here, both in the button list and implicitly in the message."""
    text = db.get_text("forcesub_prompt")
    markup = kb.force_sub_kb(unjoined_channels, continue_data)
    if is_callback:
        await target.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.reply_text(text, reply_markup=markup, parse_mode="HTML")


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

    _fid, channel_msg_id, _uploader, _ftype, _fname, caption, _uploaded_at = row
    storage_channel_id = db.get_setting("storage_channel_id")
    if not storage_channel_id:
        text = "❌ Storage channel is not configured yet. Ask an admin to set it up."
        if edit_status:
            await chat_target.edit_message_text(text)
        else:
            await chat_target.reply_text(text)
        return

    status_text = db.get_text("fetching")
    if edit_status:
        await chat_target.edit_message_text(status_text, parse_mode="HTML")
        status_msg_id = chat_target.message.message_id
    else:
        status_msg = await chat_target.reply_text(status_text, parse_mode="HTML")
        status_msg_id = status_msg.message_id

    protect = db.get_setting("protect_content", "0") == "1"
    brand_label = db.get_text("brand_label").strip()

    caption_kwargs = {}
    if brand_label:
        new_caption = f"{brand_label}\n\n{caption}" if caption else brand_label
        caption_kwargs["caption"] = new_caption

    try:
        # copy_message (not forward) so the delivered file carries its
        # original caption but no "forwarded from" trail, and works
        # regardless of the uploader's forward-privacy settings.
        sent_file = await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=int(storage_channel_id),
            message_id=channel_msg_id,
            protect_content=protect,
            **caption_kwargs,
        )
    except (BadRequest, Forbidden) as e:
        logger.error("Delivery failed for file %s to user %s: %s", file_id, user_id, e)
        fail_text = "❌ Couldn't deliver the file. Please contact an admin."
        await context.bot.edit_message_text(chat_id=user_id, message_id=status_msg_id, text=fail_text)
        return

    auto_delete_seconds = int(db.get_setting("auto_delete_seconds", "300") or 0)

    if auto_delete_seconds > 0:
        timer_text = f"⏳ <b>{auto_delete_seconds}s</b> remaining"
        if not protect:
            # Telegram's own protect_content already blocks forwarding when
            # ON, so the explicit warning only needs to show when it's OFF.
            timer_text += f"\n\n{db.get_text('no_forward_warning')}"
        timer_msg = await context.bot.send_message(user_id, timer_text, parse_mode="HTML")
        success_text = f"{db.get_text('delivered')}\n⏳ Auto-delete timer started."
    else:
        timer_msg = None
        success_text = db.get_text("delivered")

    await context.bot.edit_message_text(
        chat_id=user_id, message_id=status_msg_id, text=success_text,
        reply_markup=kb.home_kb(), parse_mode="HTML",
    )

    if timer_msg:
        asyncio.create_task(
            run_countdown(context, user_id, timer_msg.message_id, sent_file.message_id, auto_delete_seconds, protect)
        )


async def run_countdown(context, chat_id: int, timer_msg_id: int, file_msg_id: int,
                         total_seconds: int, protect: bool):
    bar_length = 20
    step = max(1, total_seconds // 60)  # cap update frequency for very long timers
    warning_line = "" if protect else f"\n\n{db.get_text('no_forward_warning')}"

    for seconds_left in range(total_seconds, 0, -step):
        emoji = "⏳" if seconds_left > total_seconds * 0.3 else ("⚠️" if seconds_left > total_seconds * 0.1 else "🔴")
        filled = max(0, min(bar_length, int((seconds_left / total_seconds) * bar_length)))
        bar = "█" * filled + "░" * (bar_length - filled)
        text = f"{emoji} | {bar} <b>{seconds_left}s</b>{warning_line}"
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=timer_msg_id, text=text, parse_mode="HTML")
        except Exception:
            pass
        await asyncio.sleep(step)

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=file_msg_id)
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=timer_msg_id,
            text=f"🗑 <b>Deleted</b>\n\n{db.get_text('auto_deleted')}",
            parse_mode="HTML",
        )
    except Exception:
        pass
