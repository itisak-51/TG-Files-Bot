"""
Registers the bot's commands with Telegram so they show up in the native
"/" command picker inside the chat — not just as things the bot happens
to respond to.

Regular users see a short public list. Admins (looked up per chat_id) get
an extended list that includes the admin-only commands. This is done via
BotCommandScopeChat, which lets each chat have its own menu.
"""
from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

PUBLIC_COMMANDS = [
    BotCommand("start", "Open the main menu"),
    BotCommand("help", "How this bot works"),
]

# Admins see exactly one extra command in the "/" picker: /admin.
# /setstorage, /checkstorage and /cancel still work when typed — they're
# just left out of the menu to keep it to the third command, per spec.
ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand("admin", "Open the admin panel (admins only)"),
]


async def apply_default_commands(bot):
    """The list every non-admin user sees."""
    await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())


async def apply_admin_commands(bot, user_id: int):
    """The wider list a specific admin sees, in their own chat only."""
    try:
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception:
        # Most likely the bot has never had a private chat with this user yet
        # (e.g. an admin was added by ID before ever messaging the bot).
        # Telegram can't attach a per-chat menu until that chat exists; it
        # will apply next time this is called after they've messaged /start.
        pass


async def clear_admin_commands(bot, user_id: int):
    """Drop a removed admin back to the public command list."""
    try:
        await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeChat(chat_id=user_id))
    except Exception:
        pass


async def sync_all_admin_commands(bot, admin_ids):
    """Called once at startup so every already-known admin has the full menu."""
    for uid in admin_ids:
        await apply_admin_commands(bot, uid)
