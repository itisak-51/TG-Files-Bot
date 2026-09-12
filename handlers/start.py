from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
import nav
from handlers.delivery import get_unjoined_channels, prompt_join, deliver_file


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text(db.get_text("banned_notice"), parse_mode="HTML")
        return

    db.track_user(user.id, user.first_name or "", user.username or "")
    args = context.args
    file_id = args[0] if args else None
    is_admin = db.is_admin(user.id)

    # Admins/owner manage the force-sub channels themselves, so they're
    # exempt from the gate — everyone else is checked fresh, every time.
    if not is_admin:
        unjoined = await get_unjoined_channels(context, user.id)
        if unjoined:
            continue_data = f"checksubfile_{file_id}" if file_id else "checksubstart"
            await prompt_join(update.message, context, unjoined, continue_data)
            return

    if file_id:
        # Deep-link file request: show ONLY status -> file -> timer.
        # No welcome text, no menus, nothing else gets attached to this flow.
        await deliver_file(context, update.message, user.id, file_id, edit_status=False)
        return

    if is_admin:
        context.user_data["level"] = "root"
        context.user_data["leaf_active"] = None
        welcome = db.get_text("welcome").format(name=user.first_name)
        await update.message.reply_text(welcome, reply_markup=nav.reply_kb("root"), parse_mode="HTML")
    else:
        # Pure receive-only experience: no menus, no upload access.
        welcome = db.get_text("welcome").format(name=user.first_name)
        await update.message.reply_text(
            welcome, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(db.get_text("help"), parse_mode="HTML")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("state", None)
    await update.message.reply_text("✅ Cancelled. Nothing pending.")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    context.user_data["level"] = "admin"
    context.user_data["leaf_active"] = None
    await update.message.reply_text(
        nav.LEVEL_ARRIVAL_TEXT["admin"], reply_markup=nav.reply_kb("admin"), parse_mode="HTML",
    )
