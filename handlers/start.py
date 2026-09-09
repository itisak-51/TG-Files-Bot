from telegram import Update
from telegram.ext import ContextTypes

import database as db
import keyboards as kb
from handlers.delivery import is_user_subscribed, prompt_join, deliver_file

HELP_TEXT = (
    "❓ <b>How This Bot Works</b>\n\n"
    "1️⃣ Send me any file (document, video, photo, audio, voice, or GIF) — I'll store it securely.\n"
    "2️⃣ I hand you back a shareable link.\n"
    "3️⃣ Anyone who opens the link must join the required channel(s)/group(s) first.\n"
    "4️⃣ Delivered files auto-delete after a timer — please don't forward them elsewhere.\n\n"
    "<b>Commands:</b>\n"
    "/start — open the main menu\n"
    "/help — show this message"
)

HELP_TEXT_ADMIN_NOTE = (
    "\n\n<b>Admin-only commands:</b>\n"
    "/admin — open the admin panel\n"
    "/setstorage &lt;id&gt; — directly set the storage channel\n"
    "/checkstorage — diagnose why the storage channel isn't working\n"
    "/cancel — cancel whatever you're currently typing for the bot"
)

ABOUT_TEXT = (
    "ℹ️ <b>About This Bot</b>\n\n"
    "A secure file-store &amp; delivery bot with force-subscribe gating, "
    "multi-admin management, and automatic copyright-safe deletion."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_banned(user.id):
        await update.message.reply_text("⛔ You are banned from using this bot.")
        return

    db.track_user(user.id, user.first_name or "", user.username or "")
    args = context.args

    if args:
        # Deep-link file request: show ONLY status -> file -> timer.
        # No welcome text, no menus, nothing else gets attached to this flow.
        file_id = args[0]
        if await is_user_subscribed(context, user.id):
            await deliver_file(context, update.message, user.id, file_id, edit_status=False)
        else:
            await prompt_join(update.message, file_id, is_callback=False)
        return

    welcome = db.get_setting("welcome_msg").format(name=user.first_name)
    await update.message.reply_text(welcome, reply_markup=kb.main_menu_kb(user.id), parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = HELP_TEXT
    if db.is_admin(user.id):
        text += HELP_TEXT_ADMIN_NOTE
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb.home_kb())


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("state", None)
    await update.message.reply_text("✅ Cancelled. Nothing pending.")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    await update.message.reply_text(
        "🛠 <b>Admin Panel</b>\n\nManage your bot live — no restarts needed.",
        reply_markup=kb.admin_main_kb(), parse_mode="HTML",
    )
