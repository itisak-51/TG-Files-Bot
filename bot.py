"""
Telegram File Store Bot — main entry point.

Reliability model:
1. python-telegram-bot's run_polling() already retries transient network
   errors internally.
2. This file wraps startup in an outer loop that catches any unhandled
   exception, logs it, waits, and restarts the bot process in-place.
3. For production, deploy under systemd (see filestore-bot.service) with
   Restart=always as the outermost safety net — it survives even a full
   Python interpreter crash or an out-of-memory kill, which an in-process
   try/except cannot.
"""
import logging
import time

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import config
import database as db
from handlers.start import start, help_command, cancel_command, admin_command
from handlers.callbacks import button_router
from handlers.text_input import text_handler
from handlers.upload import handle_file_upload
from handlers.admin_commands import setstorage_command, checkstorage_command
from handlers.commands_setup import apply_default_commands, sync_all_admin_commands
from handlers.chat_tracking import track_my_chat_member

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_PATH, encoding="utf-8")],
)
logger = logging.getLogger("filestore-bot")


async def on_error(update: object, context) -> None:
    logger.error("Unhandled exception while processing update %s", update, exc_info=context.error)


async def post_init(app: Application) -> None:
    """Runs once after the bot connects, before polling starts."""
    await apply_default_commands(app.bot)
    await sync_all_admin_commands(app.bot, db.list_admins())
    logger.info("Command menus registered.")


def build_app() -> Application:
    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("setstorage", setstorage_command))
    app.add_handler(CommandHandler("checkstorage", checkstorage_command))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(
        MessageHandler(
            filters.Document.ALL | filters.VIDEO | filters.PHOTO | filters.AUDIO
            | filters.ANIMATION | filters.VOICE | filters.VIDEO_NOTE | filters.Sticker.ALL,
            handle_file_upload,
        )
    )
    # Fires on every add/remove/promote/demote of the bot itself anywhere —
    # this is how we learn which channels/groups the bot administers, for
    # the Storage Channel and Force-Sub "pick a channel" menus.
    app.add_handler(ChatMemberHandler(track_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_error_handler(on_error)
    return app


def main():
    db.init_db()
    logger.info("Database ready at %s", config.DB_PATH)

    backoff = 5
    while True:
        try:
            app = build_app()
            logger.info("🚀 Bot starting (polling)...")
            app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
            # run_polling only returns on a clean shutdown (e.g. Ctrl+C) — exit normally.
            break
        except TelegramError as e:
            logger.exception("Telegram API error, restarting in %ss: %s", backoff, e)
        except Exception as e:
            logger.exception("Unexpected crash, restarting in %ss: %s", backoff, e)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)  # exponential backoff, capped at 60s


if __name__ == "__main__":
    main()
