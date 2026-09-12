"""
Shared helper enforcing one simple invariant: only one inline
action-screen (a pick-list, a confirmation, a force-sub join-prompt,
anything with tappable buttons tied to a specific piece of data) is ever
live at a time. Without this, navigating away from a screen — even just
tapping a bottom reply-keyboard button — leaves its old inline buttons
fully clickable forever, so a picker opened two menus ago can still be
tapped and silently act on whatever it was showing.

Lives outside both handlers/callbacks.py and handlers/delivery.py (which
otherwise can't import from each other without a cycle) since both need
it: the admin panel's pick-lists, and the force-subscribe join-prompt.
"""
from telegram import InlineKeyboardMarkup

EMPTY_MARKUP = InlineKeyboardMarkup([])


async def clear_active_inline(context, except_msg=None):
    """Strips the buttons off whatever inline screen was last shown, unless
    it's the exact message we're about to re-edit anyway (e.g. paging
    through the same picker)."""
    active = context.user_data.get("active_inline")
    if not active:
        return
    if except_msg is not None and tuple(active) == tuple(except_msg):
        return
    chat_id, msg_id = active
    context.user_data["active_inline"] = None
    try:
        await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=msg_id, reply_markup=None)
    except Exception:
        pass  # message may already be gone/edited/too old — nothing more to do


async def show(target, context, text, markup=None, parse_mode="HTML"):
    """target: a CallbackQuery (edits its message in place) or a Message
    (sends a new one). Always leaves at most one inline-bearing message
    live, tracked in context.user_data['active_inline']."""
    if hasattr(target, "edit_message_text"):
        this_msg = (target.message.chat_id, target.message.message_id)
        await clear_active_inline(context, except_msg=this_msg)
        # Telegram does NOT clear an existing inline keyboard just because
        # reply_markup was omitted from an edit — it must be replaced with
        # an explicit (possibly empty) markup object.
        await target.edit_message_text(text, reply_markup=(markup if markup is not None else EMPTY_MARKUP),
                                        parse_mode=parse_mode)
        chat_id, msg_id = this_msg
    else:
        await clear_active_inline(context)
        sent = await target.reply_text(text, reply_markup=markup, parse_mode=parse_mode)
        chat_id, msg_id = sent.chat_id, sent.message_id

    if markup is not None and hasattr(markup, "inline_keyboard"):
        context.user_data["active_inline"] = (chat_id, msg_id)
    else:
        context.user_data["active_inline"] = None
