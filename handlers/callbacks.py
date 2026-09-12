"""
Every "screen" the admin panel can show is written once as a function that
accepts either a CallbackQuery (edits its message — used for inline
pick-lists, pagination, toggles, confirmations) or a Message (sends a new
one — used when the screen is reached by tapping a bottom reply-keyboard
button). handlers/text_input.py's menu-button router calls these same
functions with a Message target, so the two navigation systems never
drift out of sync with each other.
"""
import datetime
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import config
import database as db
import devuploads
import keyboards as kb
import nav
import texts
import ui_state
from handlers.delivery import get_unjoined_channels, deliver_file, prompt_join
from handlers.commands_setup import clear_admin_commands, apply_admin_commands
from handlers.chat_tracking import refresh_all_known_chats

PAGE_SIZE = kb.PAGE_SIZE
_show = ui_state.show


async def _notify(target, context, text):
    """Feedback shown *after* the initial (blank) answerCallbackQuery has
    already been sent for this update — Telegram only allows answering a
    callback query once, so any further feedback has to go into the
    message body instead of a second popup. Routed through _show so it
    also correctly clears out anything left over."""
    await _show(target, context, text)


async def _show_note(target, context, note: str, text: str, markup=None):
    """Prepends a one-line confirmation to the next screen — the standard
    way to give feedback on a callback-triggered action without a second
    (invalid) answerCallbackQuery call."""
    combined = f"✅ {note}\n\n{text}" if note else text
    await _show(target, context, combined, markup)


async def _require_admin(target, context) -> bool:
    user = target.from_user
    if not db.is_admin(user.id):
        await _notify(target, context, "⛔ Not authorized.")
        return False
    return True


# ============================================================
# Hub / summary text builders (shared by hub screens + stats-style leaves)
# ============================================================

def _stats_text() -> str:
    return (
        "📊 <b>Live Statistics</b>\n\n"
        f"👥 Total Users: <code>{db.user_count()}</code>\n"
        f"🚫 Banned Users: <code>{db.banned_count()}</code>\n"
        f"🗄 Total Files: <code>{db.file_count()}</code>\n"
        f"🛡 Admins: <code>{len(db.list_admins())}</code>\n"
        f"🔐 Force-Sub Channels: <code>{len(db.list_force_sub_channels())}</code>\n"
        f"🟢 Status: <b>Online</b>"
    )


def _settings_text() -> str:
    storage = db.get_setting("storage_channel_id") or "Not set"
    protect_on = db.get_setting("protect_content", "0") == "1"
    protect = "ON 🔒 (can't be forwarded)" if protect_on else "OFF 🔓 (can be forwarded)"
    return (
        "⚙️ <b>Live Settings</b>\n\n"
        f"🔒 Storage Channel: <code>{storage}</code>\n"
        f"⏱ Auto-Delete Timer: <code>{db.get_setting('auto_delete_seconds', '300')}s</code>\n"
        f"🛡 Content Protection: <b>{protect}</b>"
    )


def _users_hub_text() -> str:
    return f"👥 <b>Manage Users</b>\n\nTracked: <code>{db.user_count()}</code>\nBanned: <code>{db.banned_count()}</code>"


def _admins_text() -> str:
    admin_ids = db.list_admins()
    lines = []
    for aid in admin_ids:
        role = "👑 Owner" if db.is_owner(aid) else "🛡 Admin"
        lines.append(f"{role}: {db.display_name(aid)} (<code>{aid}</code>)")
    return "🛡 <b>Manage Admins</b>\n\n" + "\n".join(lines)


def _forcesub_hub_text() -> str:
    channels = db.list_force_sub_channels()
    return f"🔐 <b>Force Channel Subscription</b>\n\nCurrently mandatory: <code>{len(channels)}</code> channel(s)/group(s)."


def _files_hub_text() -> str:
    return f"🗄 <b>Files Management</b>\n\nTotal files stored: <code>{db.file_count()}</code>"


async def screen_stats(target, context):
    await _show(target, context, _stats_text())


async def screen_settings_hub(target, context):
    await _show(target, context, _settings_text())


async def screen_users_hub(target, context):
    await _show(target, context, _users_hub_text())


async def screen_admins_hub(target, context):
    await _show(target, context, _admins_text())


async def screen_forcesub_hub(target, context):
    await _show(target, context, _forcesub_hub_text())


async def screen_files_hub(target, context):
    await _show(target, context, _files_hub_text())


async def screen_backup_hub(target, context):
    await _show(target, context, nav.LEVEL_ARRIVAL_TEXT["backup"])


# ============================================================
# Settings leaves
# ============================================================

async def screen_storage(target, context, page: int = 0):
    channels = db.list_admin_known_chats()
    current = db.get_setting("storage_channel_id") or "Not set"
    text = (
        f"🔒 <b>Storage Channel</b>\n\nCurrently: <code>{current}</code>\n\n"
        + ("Pick a channel the bot administers:" if channels else
           "I haven't seen any channels/groups where I'm admin yet. Forward a message from one, "
           "promote the bot there, or enter its ID manually below.")
    )
    await _show(target, context, text, kb.storage_pick_kb(channels, page))


async def screen_welcome_prompt(target, context):
    context.user_data["state"] = "AWAITING_WELCOME"
    current = db.get_text("welcome")
    text = (
        f"✍️ <b>Current Welcome Message:</b>\n\n{current}\n\n"
        "Send the new welcome message. Use <code>{name}</code> for the user's name. HTML tags are allowed."
    )
    await _show(target, context, text, kb.cancel_kb())


async def screen_autodelete_prompt(target, context):
    context.user_data["state"] = "AWAITING_AUTODELETE"
    current = db.get_setting("auto_delete_seconds", "300")
    text = (
        f"⏱ Current timer: <code>{current}s</code>\n\n"
        "Send the auto-delete timer in <b>seconds</b> (e.g. <code>300</code> for 5 minutes). "
        "Send <code>0</code> to disable auto-delete."
    )
    await _show(target, context, text, kb.cancel_kb())


async def do_toggle_protect(target, context):
    current = db.get_setting("protect_content", "0")
    new_val = "0" if current == "1" else "1"
    db.set_setting("protect_content", new_val)
    state_word = "ON 🔒" if new_val == "1" else "OFF 🔓"
    await _show(target, context, f"🛡 Content Protection is now <b>{state_word}</b>.\n\n" + _settings_text())


async def screen_edit_mode(target, context):
    text = "🎛 <b>Edit Mode</b>\n\nTap a text below to view and change its current wording:"
    await _show(target, context, text, kb.edit_mode_pick_kb())


# ============================================================
# Force-Sub leaves
# ============================================================

async def screen_fsub_show(target, context):
    channels = db.list_force_sub_channels()
    lines = [f"• <code>{cid}</code> — {title or 'Untitled'}" for cid, title, _link in channels] or [
        "<i>None configured — everyone can access files freely.</i>"
    ]
    await _show(target, context, "📄 <b>Force-Sub Channels</b>\n\n" + "\n".join(lines))


async def screen_fsub_add_picker(target, context, page: int = 0):
    existing_ids = {cid for cid, _t, _l in db.list_force_sub_channels()}
    candidates = [c for c in db.list_admin_known_chats() if c[0] not in existing_ids]
    text = (
        "➕ <b>Add Force-Sub Channel</b>\n\nTap a channel/group the bot administers to make it mandatory:"
        if candidates else
        "➕ <b>Add Force-Sub Channel</b>\n\nNo new admin channels/groups detected. "
        "Forward a message from one, promote the bot there, or enter it manually."
    )
    await _show(target, context, text, kb.forcesub_add_pick_kb(candidates, page))


async def screen_fsub_remove_picker(target, context, page: int = 0):
    channels = db.list_force_sub_channels()
    text = "➖ <b>Remove Force-Sub Channel</b>\n\nTap one to remove it:" if channels else \
        "➖ <b>Remove Force-Sub Channel</b>\n\nNothing configured yet."
    await _show(target, context, text, kb.forcesub_remove_pick_kb(channels, page))


# ============================================================
# Users leaves
# ============================================================

async def screen_list_users(target, context, page: int = 0):
    users = db.list_users_full()
    chunk = users[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]
    if not users:
        text = "📋 <b>All Users</b>\n\n<i>No users tracked yet.</i>"
    else:
        lines = [
            f"{'🚫' if banned else '•'} {fname or (('@' + uname) if uname else 'Unknown')} — <code>{uid}</code>"
            for uid, fname, uname, banned in chunk
        ]
        text = f"📋 <b>All Users</b> ({len(users)} total)\n\n" + "\n".join(lines)
    await _show(target, context, text, kb.user_list_kb(len(users), page))


async def screen_ban_picker(target, context, page: int = 0):
    users = db.list_bannable_users()
    text = "🚫 <b>Ban a User</b>\n\nTap a user to ban them:" if users else "🚫 <b>Ban a User</b>\n\nNo bannable users found."
    await _show(target, context, text, kb.ban_pick_kb(users, page))


async def screen_unban_picker(target, context, page: int = 0):
    users = db.list_banned_users()
    text = "✅ <b>Unban a User</b>\n\nTap a user to unban them:" if users else "✅ <b>Unban a User</b>\n\nNo banned users."
    await _show(target, context, text, kb.unban_pick_kb(users, page))


async def do_export_users(target, context):
    rows = db.list_users_full()
    if not rows:
        await _notify(target, context, "No users to export yet.")
        return
    path = "/tmp/users_export.txt"
    with open(path, "w", encoding="utf-8") as f:
        for uid, fname, uname, banned in rows:
            name = fname or (("@" + uname) if uname else "Unknown")
            f.write(f"{name} | {uid} | {'Banned' if banned else 'Active'}\n")
    with open(path, "rb") as f:
        await context.bot.send_document(chat_id=target.from_user.id, document=f,
                                         filename="users_export.txt",
                                         caption="📥 Exported Users (Name | ID | Status)")
    os.remove(path)


# ============================================================
# Admins leaves
# ============================================================

async def screen_add_admin_picker(target, context, page: int = 0):
    users = db.list_promotable_users()
    text = ("➕ <b>Add Admin</b>\n\nTap a user to promote them:" if users else
            "➕ <b>Add Admin</b>\n\nNo eligible users found — they need to have messaged the bot first.")
    await _show(target, context, text, kb.add_admin_pick_kb(users, page))


async def screen_remove_admin_picker(target, context, page: int = 0):
    admin_ids = db.list_admins()
    text = "➖ <b>Remove Admin</b>\n\nTap an admin to demote them:"
    await _show(target, context, text, kb.remove_admin_pick_kb(admin_ids, config.OWNER_ID, page))


# ============================================================
# Broadcast
# ============================================================

async def screen_broadcast_prompt(target, context):
    context.user_data["state"] = "AWAITING_BROADCAST"
    text = "📢 <b>Broadcast</b>\n\nSend the message you want to broadcast to all tracked users.\n\n<i>Send /cancel to abort.</i>"
    await _show(target, context, text, kb.cancel_kb())


# ============================================================
# Files Management leaves
# ============================================================

async def screen_files_getlink_picker(target, context, page: int = 0):
    files = db.list_all_files()
    text = "🔗 <b>Get Link</b>\n\nTap a file to get its link:" if files else "🔗 <b>Get Link</b>\n\nNo files stored yet."
    await _show(target, context, text, kb.file_pick_kb(files, "linkpick_", "linkpg_", page))


async def screen_files_remove_picker(target, context, page: int = 0):
    files = db.list_all_files()
    text = ("🗑 <b>Remove File</b>\n\nTap a file to remove it (deletes the link and the stored copy):"
            if files else "🗑 <b>Remove File</b>\n\nNo files stored yet.")
    await _show(target, context, text, kb.file_pick_kb(files, "rmfilepick_", "rmfilepg_", page))


async def screen_files_changeid_picker(target, context, page: int = 0):
    files = db.list_all_files()
    text = ("🆔 <b>Change File ID</b>\n\nTap a file to issue it a new link (the old link stops working):"
            if files else "🆔 <b>Change File ID</b>\n\nNo files stored yet.")
    await _show(target, context, text, kb.file_pick_kb(files, "chidpick_", "chidpg_", page))


# ============================================================
# Backup / Restore / Destroy
# ============================================================

async def do_backup(target, context):
    fname = f"backup_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
    path = f"/tmp/{fname}"
    db.create_backup(path)
    with open(path, "rb") as f:
        await context.bot.send_document(
            chat_id=target.from_user.id, document=f, filename=fname,
            caption="💾 <b>Backup complete.</b>\n\nContains all metadata, configuration, and pointers to your "
                    "files (not the file bytes themselves — those stay on Telegram). Keep it safe; ♻️ Restore Data "
                    "loads it back exactly where you left off, even on a brand-new host.",
            parse_mode="HTML",
        )
    os.remove(path)


async def screen_restore_prompt(target, context):
    context.user_data["state"] = "AWAITING_RESTORE_FILE"
    text = (
        "♻️ <b>Restore Data</b>\n\nSend me the <code>.db</code> backup file. "
        "I'll pick up from exactly where that backup left off — same users, admins, files, and settings."
    )
    await _show(target, context, text, kb.cancel_kb())


async def screen_destroy_confirm(target, context):
    text = (
        "🔥 <b>Destroy Data</b>\n\n⚠️ This deletes every stored file from the storage channel, and wipes all "
        "users, admins (except you), and settings. The bot resets to a fresh install.\n\n<b>This cannot be undone.</b>"
    )
    await _show(target, context, text, kb.confirm_kb("destroy_confirm", "destroy_cancel"))


async def do_destroy(query, context):
    storage_channel_id = db.get_setting("storage_channel_id")
    deleted = 0
    if storage_channel_id:
        for fid, _ftype, _fname, _ts in db.list_all_files():
            row = db.get_file(fid)
            if row:
                try:
                    await context.bot.delete_message(chat_id=int(storage_channel_id), message_id=row[1])
                    deleted += 1
                except Exception:
                    pass
    db.destroy_all_local_data()
    await _show(
        query, context,
        f"🔥 <b>Destroyed.</b>\n\nRemoved {deleted} file(s) from the storage channel and wiped all local data. "
        "The bot is now a fresh install — you're still the owner.",
    )


# ============================================================
# DevUploads
# ============================================================

def _masked_key(key: str) -> str:
    if not key:
        return "Not set"
    return f"...{key[-4:]}" if len(key) > 4 else "****"


def _devuploads_hub_text() -> str:
    key = db.get_setting("devuploads_api_key")
    mirrored = len(db.list_devuploads_mirrored_files())
    return (
        "🌐 <b>DevUploads</b>\n\n"
        f"🔑 API Key: <code>{_masked_key(key)}</code>\n"
        f"🪞 Mirrored files: <code>{mirrored}</code>\n\n"
        + ("Every new upload is automatically mirrored to DevUploads too."
           if key else "Set an API key to start mirroring new uploads to DevUploads.")
    )


async def screen_devuploads_hub(target, context):
    await _show(target, context, _devuploads_hub_text())


async def screen_devuploads_account(target, context):
    key = db.get_setting("devuploads_api_key")
    if not key:
        await _show(target, context, "🔑 No DevUploads API key set yet. Use <b>🔑 Set API Key</b> first.")
        return
    info = await devuploads.account_info(key)
    if not info.ok:
        await _show(target, context, f"❌ Couldn't reach DevUploads: {info.error}")
        return
    d = info.data or {}
    stats = await devuploads.account_stats(key)
    stats_line = ""
    if stats.ok and stats.data:
        s = stats.data[0] if isinstance(stats.data, list) else stats.data
        stats_line = (
            f"\n📥 Downloads: <code>{s.get('downloads', '?')}</code>\n"
            f"💰 Total Profit: <code>{s.get('profit_total', '?')}</code>"
        )
    text = (
        "📊 <b>DevUploads Account</b>\n\n"
        f"✉️ Email: <code>{d.get('email', '?')}</code>\n"
        f"💵 Balance: <code>{d.get('balance', '?')}</code>\n"
        f"💾 Storage Used: <code>{d.get('storage_used') or '0'}</code>\n"
        f"📦 Storage Left: <code>{d.get('storage_left', '?')}</code>\n"
        f"⭐ Premium Expires: <code>{d.get('premium_expire', '?')}</code>"
        f"{stats_line}"
    )
    await _show(target, context, text)


async def screen_devuploads_setkey_prompt(target, context):
    context.user_data["state"] = "AWAITING_DEVUPLOADS_KEY"
    current = db.get_setting("devuploads_api_key")
    await _show(
        target, context,
        f"🔑 <b>DevUploads API Key</b>\n\nCurrent: <code>{_masked_key(current)}</code>\n\n"
        "Send the new key (find it in your DevUploads account settings), or send <code>0</code> to clear it.",
        kb.cancel_kb(),
    )


async def screen_devuploads_files_menu(target, context):
    await _show(target, context, "📁 <b>Manage Files</b>", kb.devuploads_files_menu_kb())


async def screen_devuploads_files_list(target, context, page: int = 1):
    key = db.get_setting("devuploads_api_key")
    if not key:
        await _show(target, context, "🔑 No DevUploads API key set yet.")
        return
    result = await devuploads.file_list(key, page=page, per_page=10)
    if not result.ok:
        await _show(target, context, f"❌ {result.error}")
        return
    files = (result.data or {}).get("files", [])
    total = (result.data or {}).get("results_total", len(files))
    if not files:
        text = "📋 <b>DevUploads Files</b>\n\n<i>No files found.</i>"
    else:
        lines = [f"• {f.get('name')} — <code>{f.get('file_code')}</code> ({f.get('size', '?')} bytes)" for f in files]
        text = f"📋 <b>DevUploads Files</b> ({total} total, page {page})\n\n" + "\n".join(lines)
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"devfileslistpg_{page - 1}"))
    if len(files) == 10:
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data=f"devfileslistpg_{page + 1}"))
    markup = InlineKeyboardMarkup([nav_row]) if nav_row else None
    await _show(target, context, text, markup)


async def screen_devuploads_rename_picker(target, context, page: int = 0):
    files = db.list_devuploads_mirrored_files()
    text = ("✏️ <b>Rename a Mirrored File</b>\n\nTap a file to rename it on DevUploads:" if files else
            "✏️ <b>Rename a Mirrored File</b>\n\nNo mirrored files yet.")
    await _show(target, context, text, kb.devuploads_file_pick_kb(files, "devfilesrenamepick_", "devfilesrenamepg_", page))


async def screen_devuploads_delete_picker(target, context, page: int = 0):
    files = db.list_devuploads_mirrored_files()
    text = ("🗑 <b>Delete a Mirrored File</b>\n\nTap a file to remove its DevUploads mirror "
            "(the Telegram copy is untouched):" if files else "🗑 <b>Delete a Mirrored File</b>\n\nNo mirrored files yet.")
    await _show(target, context, text, kb.devuploads_file_pick_kb(files, "devfilesdeletepick_", "devfilesdeletepg_", page))


async def screen_devuploads_folders_menu(target, context):
    await _show(target, context, "📂 <b>Manage Folders</b>", kb.devuploads_folders_menu_kb())


async def screen_devuploads_folders_list(target, context):
    key = db.get_setting("devuploads_api_key")
    if not key:
        await _show(target, context, "🔑 No DevUploads API key set yet.")
        return
    result = await devuploads.folder_list(key)
    if not result.ok:
        await _show(target, context, f"❌ {result.error}")
        return
    folders = (result.data or {}).get("folders", [])
    text = "📂 <b>Folders</b>\n\n" + (
        "\n".join(f"• {f.get('name')} — <code>{f.get('fld_id')}</code>" for f in folders)
        if folders else "<i>No sub-folders at the root level.</i>"
    )
    await _show(target, context, text)


async def screen_devuploads_create_folder_prompt(target, context):
    context.user_data["state"] = "AWAITING_DEVUPLOADS_NEWFOLDER"
    await _show(target, context, "➕ Send the name for the new DevUploads folder.", kb.cancel_kb())


async def screen_devuploads_delete_folder_prompt(target, context):
    context.user_data["state"] = "AWAITING_DEVUPLOADS_DELFOLDER"
    await _show(
        target, context,
        "🗑 Send the <code>fld_id</code> of the folder to delete (use 📋 List Folders to find it).",
        kb.cancel_kb(),
    )


async def screen_devuploads_remote_prompt(target, context):
    context.user_data["state"] = "AWAITING_DEVUPLOADS_REMOTE_URL"
    await _show(
        target, context,
        "🔗 <b>Remote Upload</b>\n\nSend a direct URL and DevUploads will fetch it on their end "
        "(no need to download it yourself first).",
        kb.cancel_kb(),
    )


# ============================================================
# CallbackQueryHandler entry point
# ============================================================

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    if db.is_banned(user.id):
        await query.answer(db.get_text("banned_notice"), show_alert=True)
        return

    await query.answer()
    data = query.data

    # ---------------- Available to everyone ----------------
    if data == "home":
        context.user_data["level"] = "root"
        await _show(query, context, "🏠 Opening the main menu...")
        welcome = db.get_text("welcome").format(name=user.first_name)
        markup = nav.reply_kb("root") if db.is_admin(user.id) else None
        await context.bot.send_message(user.id, welcome, reply_markup=markup, parse_mode="HTML")
        return

    if data == "checksubstart" or data.startswith("checksubfile_"):
        unjoined = await get_unjoined_channels(context, user.id)
        if unjoined:
            await prompt_join(query, context, unjoined, data)
            return
        if data == "checksubstart":
            await _show(query, context, "✅ Access granted!")
            welcome = db.get_text("welcome").format(name=user.first_name)
            await context.bot.send_message(user.id, welcome, parse_mode="HTML")
        else:
            file_id = data[len("checksubfile_"):]
            await _show(query, context, "✅ Access granted! Fetching...")
            await deliver_file(context, query, user.id, file_id, edit_status=True)
        return

    if data == "cancel_action":
        context.user_data.pop("state", None)
        await _show(query, context, "✅ Action cancelled.")
        return

    if data == "menu_upload":
        if db.is_admin(user.id):
            context.user_data["state"] = "AWAITING_UPLOAD"
            await _show(
                query, context,
                "📤 <b>Upload a File</b>\n\nSend me any document, video, photo, audio, voice note, GIF, or sticker "
                "right here. I'll secure it and hand you a shareable link!",
            )
        else:
            await _show(query, context, db.get_text("upload_blocked"))
        return

    if data == "menu_help":
        await _show(query, context, db.get_text("help"))
        return

    if data == "menu_about":
        await _show(query, context, db.get_text("about"))
        return

    # ---------------- Everything else requires admin ----------------
    if not await _require_admin(query, context):
        return

    if data == "admin_main":
        await _show(query, context, nav.LEVEL_ARRIVAL_TEXT["admin"])
    elif data == "admin_stats":
        await screen_stats(query, context)
    elif data == "admin_settings":
        await screen_settings_hub(query, context)
    elif data == "set_storage":
        await screen_storage(query, context)
    elif data.startswith("stopg_"):
        await screen_storage(query, context, int(data[len("stopg_"):]))
    elif data == "storage_refresh":
        count = await refresh_all_known_chats(context)
        channels = db.list_admin_known_chats()
        current = db.get_setting("storage_channel_id") or "Not set"
        text = f"🔒 <b>Storage Channel</b>\n\nCurrently: <code>{current}</code>\n\nPick a channel:"
        await _show_note(query, context, f"Refreshed — {count} admin channel(s)/group(s) detected.", text, kb.storage_pick_kb(channels))
    elif data == "set_storage_manual":
        context.user_data["state"] = "AWAITING_STORAGE"
        await _show(
            query, context,
            "🔒 Forward any message from your storage channel here, "
            "or send its numeric ID (e.g. <code>-1001234567890</code>).\n\nThe bot must be an <b>admin</b> there.",
            kb.cancel_kb(),
        )
    elif data.startswith("stopick_"):
        channel_id = int(data[len("stopick_"):])
        db.set_setting("storage_channel_id", str(channel_id))
        chat = db.get_known_chat(channel_id)
        await _show_note(query, context, f"Storage channel set to {chat[1] if chat else channel_id}", _settings_text())
    elif data == "set_welcome":
        await screen_welcome_prompt(query, context)
    elif data == "set_autodelete":
        await screen_autodelete_prompt(query, context)
    elif data == "toggle_protect":
        await do_toggle_protect(query, context)
    elif data == "edit_mode":
        await screen_edit_mode(query, context)
    elif data.startswith("edittext_"):
        key = data[len("edittext_"):]
        label, _default = texts.EDITABLE_TEXTS.get(key, (key, ""))
        context.user_data["state"] = f"AWAITING_EDIT_TEXT:{key}"
        current = db.get_text(key)
        await _show(
            query, context,
            f"✍️ <b>{label}</b>\n\nCurrent:\n{current if current else '<i>(empty)</i>'}\n\nSend the new text.",
            kb.cancel_kb(),
        )

    elif data == "admin_forcesub":
        await screen_forcesub_hub(query, context)
    elif data == "fsub_show":
        await screen_fsub_show(query, context)
    elif data == "fsub_add" or data.startswith("addfsubpg_"):
        page = int(data[len("addfsubpg_"):]) if data.startswith("addfsubpg_") else 0
        await screen_fsub_add_picker(query, context, page)
    elif data == "fsub_add_refresh":
        count = await refresh_all_known_chats(context)
        existing_ids = {cid for cid, _t, _l in db.list_force_sub_channels()}
        candidates = [c for c in db.list_admin_known_chats() if c[0] not in existing_ids]
        text = "➕ <b>Add Force-Sub Channel</b>\n\nTap a channel/group the bot administers to make it mandatory:"
        await _show_note(query, context, f"Refreshed — {count} admin channel(s)/group(s) detected.", text,
                          kb.forcesub_add_pick_kb(candidates))
    elif data == "fsub_add_manual":
        context.user_data["state"] = "AWAITING_ADD_FORCESUB_MANUAL"
        await _show(
            query, context,
            "🔐 Send the channel/group ID (forward a message from it, or type the numeric ID). "
            "I'll verify I'm actually an admin there before adding it.",
            kb.cancel_kb(),
        )
    elif data.startswith("addfsubpick_"):
        channel_id = int(data[len("addfsubpick_"):])
        chat = db.get_known_chat(channel_id)
        title = chat[1] if chat else str(channel_id)
        link = chat[3] if chat else ""
        db.add_force_sub_channel(channel_id, title, link)
        existing_ids = {cid for cid, _t, _l in db.list_force_sub_channels()}
        candidates = [c for c in db.list_admin_known_chats() if c[0] not in existing_ids]
        await _show_note(query, context, f"Added {title} to Force-Sub.",
                          "➕ <b>Add Force-Sub Channel</b>\n\nTap another to add, or go back:",
                          kb.forcesub_add_pick_kb(candidates))
    elif data == "fsub_remove" or data.startswith("rmfsubpg_"):
        page = int(data[len("rmfsubpg_"):]) if data.startswith("rmfsubpg_") else 0
        await screen_fsub_remove_picker(query, context, page)
    elif data.startswith("rmfsub_"):
        channel_id = int(data[len("rmfsub_"):])
        db.remove_force_sub_channel(channel_id)
        channels = db.list_force_sub_channels()
        text = "➖ <b>Remove Force-Sub Channel</b>\n\nTap another to remove, or go back:" if channels else \
            "➖ <b>Remove Force-Sub Channel</b>\n\nNothing left to remove."
        await _show_note(query, context, "Removed.", text, kb.forcesub_remove_pick_kb(channels))

    elif data == "admin_users":
        await screen_users_hub(query, context)
    elif data == "list_users" or data.startswith("userlistpg_"):
        page = int(data[len("userlistpg_"):]) if data.startswith("userlistpg_") else 0
        await screen_list_users(query, context, page)
    elif data == "ban_user" or data.startswith("banpg_"):
        page = int(data[len("banpg_"):]) if data.startswith("banpg_") else 0
        await screen_ban_picker(query, context, page)
    elif data.startswith("banpick_"):
        uid = int(data[len("banpick_"):])
        name = db.display_name(uid)
        db.ban_user(uid)
        users = db.list_bannable_users()
        text = "🚫 <b>Ban a User</b>\n\nTap another to ban, or go back:" if users else "🚫 <b>Ban a User</b>\n\nNo more bannable users."
        await _show_note(query, context, f"Banned {name}.", text, kb.ban_pick_kb(users))
    elif data == "unban_user" or data.startswith("unbanpg_"):
        page = int(data[len("unbanpg_"):]) if data.startswith("unbanpg_") else 0
        await screen_unban_picker(query, context, page)
    elif data.startswith("unbanpick_"):
        uid = int(data[len("unbanpick_"):])
        name = db.display_name(uid)
        db.unban_user(uid)
        users = db.list_banned_users()
        text = "✅ <b>Unban a User</b>\n\nTap another to unban, or go back:" if users else "✅ <b>Unban a User</b>\n\nNo banned users left."
        await _show_note(query, context, f"Unbanned {name}.", text, kb.unban_pick_kb(users))
    elif data == "export_users":
        await do_export_users(query, context)

    elif data == "admin_admins":
        await screen_admins_hub(query, context)
    elif data == "add_admin" or data.startswith("addadminpg_"):
        page = int(data[len("addadminpg_"):]) if data.startswith("addadminpg_") else 0
        await screen_add_admin_picker(query, context, page)
    elif data.startswith("addadminpick_"):
        uid = int(data[len("addadminpick_"):])
        name = db.display_name(uid)
        db.add_admin(uid, added_by=user.id)
        await apply_admin_commands(context.bot, uid)
        users = db.list_promotable_users()
        text = "➕ <b>Add Admin</b>\n\nTap another to promote, or go back:"
        await _show_note(query, context, f"{name} is now an admin.", text, kb.add_admin_pick_kb(users))
    elif data == "remove_admin" or data.startswith("rmadminpg_"):
        page = int(data[len("rmadminpg_"):]) if data.startswith("rmadminpg_") else 0
        await screen_remove_admin_picker(query, context, page)
    elif data.startswith("rmadmin_"):
        target_id = int(data[len("rmadmin_"):])
        name = db.display_name(target_id)
        removed = db.remove_admin(target_id)
        admin_ids = db.list_admins()
        text = "➖ <b>Remove Admin</b>\n\nTap another to demote, or go back:"
        if removed:
            await clear_admin_commands(context.bot, target_id)
            try:
                from telegram import ReplyKeyboardRemove
                await context.bot.send_message(target_id, "You are no longer an admin.", reply_markup=ReplyKeyboardRemove())
            except Exception:
                pass
            await _show_note(query, context, f"Removed admin {name}", text, kb.remove_admin_pick_kb(admin_ids, config.OWNER_ID))
        else:
            await _show_note(query, context, "The owner cannot be removed.", text, kb.remove_admin_pick_kb(admin_ids, config.OWNER_ID))

    elif data == "admin_broadcast":
        await screen_broadcast_prompt(query, context)

    elif data == "admin_files":
        await screen_files_hub(query, context)
    elif data == "file_getlink" or data.startswith("linkpg_"):
        page = int(data[len("linkpg_"):]) if data.startswith("linkpg_") else 0
        await screen_files_getlink_picker(query, context, page)
    elif data.startswith("linkpick_"):
        file_id = data[len("linkpick_"):]
        row = db.get_file(file_id)
        if not row:
            await _show(query, context, "❌ File not found — it may have been removed.")
            return
        link = f"https://t.me/{context.bot.username}?start={file_id}"
        name = row[4] or file_id
        dev_link = row[8]
        text = f"🔗 <b>{name}</b>\n\n<b>Telegram:</b>\n<code>{link}</code>"
        if dev_link:
            text += f"\n\n<b>DevUploads:</b>\n<code>{dev_link}</code>"
        await _show(query, context, text)
    elif data == "file_remove" or data.startswith("rmfilepg_"):
        page = int(data[len("rmfilepg_"):]) if data.startswith("rmfilepg_") else 0
        await screen_files_remove_picker(query, context, page)
    elif data.startswith("rmfilepick_"):
        file_id = data[len("rmfilepick_"):]
        row = db.get_file(file_id)
        if row:
            storage_channel_id = db.get_setting("storage_channel_id")
            if storage_channel_id:
                try:
                    await context.bot.delete_message(chat_id=int(storage_channel_id), message_id=row[1])
                except Exception:
                    pass
            dev_key, dev_code = db.get_setting("devuploads_api_key"), row[7]
            if dev_key and dev_code:
                try:
                    await devuploads.file_delete(dev_key, dev_code)
                except Exception:
                    pass  # best-effort mirror cleanup — Telegram-side removal above is the source of truth
            note = f"Removed {row[4] or file_id}."
            db.delete_file(file_id)
        else:
            note = "Already removed."
        files = db.list_all_files()
        text = "🗑 <b>Remove File</b>\n\nTap another to remove, or go back:" if files else "🗑 <b>Remove File</b>\n\nNo files left."
        await _show_note(query, context, note, text, kb.file_pick_kb(files, "rmfilepick_", "rmfilepg_"))
    elif data == "file_changeid" or data.startswith("chidpg_"):
        page = int(data[len("chidpg_"):]) if data.startswith("chidpg_") else 0
        await screen_files_changeid_picker(query, context, page)
    elif data.startswith("chidpick_"):
        old_file_id = data[len("chidpick_"):]
        new_id = db.regenerate_file_id(old_file_id)
        if not new_id:
            await _show(query, context, "❌ File not found — it may have been removed.")
            return
        row = db.get_file(new_id)
        name = row[4] or new_id
        link = f"https://t.me/{context.bot.username}?start={new_id}"
        await _show(
            query, context,
            f"🆔 <b>New link issued for {name}</b>\n\n<code>{link}</code>\n\n<i>The old link no longer works.</i>",
        )

    elif data == "admin_backup":
        await screen_backup_hub(query, context)
    elif data == "backup_data":
        await do_backup(query, context)
    elif data == "restore_data":
        await screen_restore_prompt(query, context)
    elif data == "destroy_data":
        await screen_destroy_confirm(query, context)
    elif data == "destroy_confirm":
        await do_destroy(query, context)
    elif data == "destroy_cancel":
        await screen_backup_hub(query, context)

    elif data == "admin_devuploads":
        await screen_devuploads_hub(query, context)
    elif data == "devuploads_account":
        await screen_devuploads_account(query, context)
    elif data == "devuploads_setkey":
        await screen_devuploads_setkey_prompt(query, context)
    elif data == "devuploads_files":
        await screen_devuploads_files_menu(query, context)
    elif data == "devfiles_list" or data.startswith("devfileslistpg_"):
        page = int(data[len("devfileslistpg_"):]) if data.startswith("devfileslistpg_") else 1
        await screen_devuploads_files_list(query, context, page)
    elif data == "devfiles_rename" or data.startswith("devfilesrenamepg_"):
        page = int(data[len("devfilesrenamepg_"):]) if data.startswith("devfilesrenamepg_") else 0
        await screen_devuploads_rename_picker(query, context, page)
    elif data.startswith("devfilesrenamepick_"):
        file_id = data[len("devfilesrenamepick_"):]
        context.user_data["state"] = f"AWAITING_DEVUPLOADS_RENAME:{file_id}"
        await _show(query, context, "✏️ Send the new name for this file on DevUploads.", kb.cancel_kb())
    elif data == "devfiles_delete" or data.startswith("devfilesdeletepg_"):
        page = int(data[len("devfilesdeletepg_"):]) if data.startswith("devfilesdeletepg_") else 0
        await screen_devuploads_delete_picker(query, context, page)
    elif data.startswith("devfilesdeletepick_"):
        file_id = data[len("devfilesdeletepick_"):]
        row = db.get_file(file_id)
        key = db.get_setting("devuploads_api_key")
        if row and key and row[7]:
            result = await devuploads.file_delete(key, row[7])
            if result.ok:
                db.set_devuploads_info(file_id, None, None)
                note = f"Deleted {row[4] or file_id} from DevUploads."
            else:
                note = f"DevUploads error: {result.error}"
        else:
            note = "Nothing to delete — no mirror found for that file."
        files = db.list_devuploads_mirrored_files()
        text = "🗑 <b>Delete a Mirrored File</b>\n\nTap another, or go back:" if files else \
            "🗑 <b>Delete a Mirrored File</b>\n\nNo mirrored files left."
        await _show_note(query, context, note, text, kb.devuploads_file_pick_kb(files, "devfilesdeletepick_", "devfilesdeletepg_"))
    elif data == "devuploads_folders":
        await screen_devuploads_folders_menu(query, context)
    elif data == "devfolders_list":
        await screen_devuploads_folders_list(query, context)
    elif data == "devfolders_create":
        await screen_devuploads_create_folder_prompt(query, context)
    elif data == "devfolders_delete":
        await screen_devuploads_delete_folder_prompt(query, context)
    elif data == "devuploads_remote":
        await screen_devuploads_remote_prompt(query, context)
