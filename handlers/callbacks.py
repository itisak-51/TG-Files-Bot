from telegram import Update
from telegram.ext import ContextTypes

import config
import database as db
import keyboards as kb
from handlers.delivery import is_user_subscribed, deliver_file
from handlers.start import HELP_TEXT, HELP_TEXT_ADMIN_NOTE, ABOUT_TEXT
from handlers.commands_setup import clear_admin_commands, apply_admin_commands

PAGE_SIZE = kb.PAGE_SIZE


async def _require_admin(query) -> bool:
    if not db.is_admin(query.from_user.id):
        await query.answer("⛔ Not authorized.", show_alert=True)
        return False
    return True


async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    if db.is_banned(user.id):
        await query.answer("⛔ You are banned.", show_alert=True)
        return

    await query.answer()
    data = query.data

    # ============================================================
    # Home / general
    # ============================================================
    if data == "home":
        welcome = db.get_setting("welcome_msg").format(name=user.first_name)
        await query.edit_message_text(welcome, reply_markup=kb.main_menu_kb(user.id), parse_mode="HTML")

    elif data == "menu_upload":
        await query.edit_message_text(
            "📤 <b>Upload a File</b>\n\nSend me any document, video, photo, audio, voice note or GIF right here. "
            "I'll secure it and hand you a shareable link!",
            parse_mode="HTML", reply_markup=kb.back_kb("home"),
        )

    elif data == "menu_help":
        text = HELP_TEXT + (HELP_TEXT_ADMIN_NOTE if db.is_admin(user.id) else "")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb.back_kb("home"))

    elif data == "menu_about":
        await query.edit_message_text(ABOUT_TEXT, parse_mode="HTML", reply_markup=kb.back_kb("home"))

    # ============================================================
    # Admin root / statistics
    # ============================================================
    elif data == "admin_main":
        if not await _require_admin(query):
            return
        await query.edit_message_text(
            "🛠 <b>Admin Panel</b>\n\nManage your bot live — no restarts needed.",
            reply_markup=kb.admin_main_kb(), parse_mode="HTML",
        )

    elif data == "admin_stats":
        if not await _require_admin(query):
            return
        text = (
            "📊 <b>Live Statistics</b>\n\n"
            f"👥 Total Users: <code>{db.user_count()}</code>\n"
            f"🚫 Banned Users: <code>{db.banned_count()}</code>\n"
            f"🗄 Total Files: <code>{db.file_count()}</code>\n"
            f"🛡 Admins: <code>{len(db.list_admins())}</code>\n"
            f"🔐 Force-Sub Channels: <code>{len(db.list_force_sub_channels())}</code>\n"
            f"🟢 Status: <b>Online</b>"
        )
        await query.edit_message_text(text, reply_markup=kb.admin_main_kb(), parse_mode="HTML")

    # ============================================================
    # Settings
    # ============================================================
    elif data == "admin_settings":
        if not await _require_admin(query):
            return
        await query.edit_message_text(_settings_text(), reply_markup=kb.settings_menu_kb(), parse_mode="HTML")

    elif data == "set_storage":
        if not await _require_admin(query):
            return
        channels = db.list_admin_known_chats()
        current = db.get_setting("storage_channel_id") or "Not set"
        text = (
            f"🔒 <b>Storage Channel</b>\n\nCurrently: <code>{current}</code>\n\n"
            + ("Pick a channel the bot administers, or add it manually:"
               if channels else
               "I haven't seen any channels/groups where I'm admin yet. "
               "Add me as admin somewhere, or enter one manually below.")
        )
        await query.edit_message_text(text, reply_markup=kb.storage_pick_kb(channels), parse_mode="HTML")

    elif data.startswith("stopg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("stopg_"):])
        channels = db.list_admin_known_chats()
        current = db.get_setting("storage_channel_id") or "Not set"
        text = f"🔒 <b>Storage Channel</b>\n\nCurrently: <code>{current}</code>\n\nPick a channel:"
        await query.edit_message_text(text, reply_markup=kb.storage_pick_kb(channels, page), parse_mode="HTML")

    elif data == "set_storage_manual":
        if not await _require_admin(query):
            return
        context.user_data["state"] = "AWAITING_STORAGE"
        await query.edit_message_text(
            "🔒 Forward any message from your storage channel here, "
            "or send its numeric ID (e.g. <code>-1001234567890</code>).\n\n"
            "The bot must be an <b>admin</b> in that channel.",
            parse_mode="HTML", reply_markup=kb.cancel_kb(),
        )

    elif data.startswith("stopick_"):
        if not await _require_admin(query):
            return
        channel_id = int(data[len("stopick_"):])
        db.set_setting("storage_channel_id", str(channel_id))
        chat = db.get_known_chat(channel_id)
        label = chat[1] if chat else str(channel_id)
        await query.answer(f"Storage channel set to {label}", show_alert=True)
        await query.edit_message_text(_settings_text(), reply_markup=kb.settings_menu_kb(), parse_mode="HTML")

    elif data == "set_welcome":
        if not await _require_admin(query):
            return
        context.user_data["state"] = "AWAITING_WELCOME"
        current = db.get_setting("welcome_msg")
        await query.edit_message_text(
            f"✍️ <b>Current Welcome Message:</b>\n\n{current}\n\n"
            "Send the new welcome message. Use <code>{name}</code> for the user's name. HTML tags are allowed.",
            parse_mode="HTML", reply_markup=kb.cancel_kb(),
        )

    elif data == "set_autodelete":
        if not await _require_admin(query):
            return
        context.user_data["state"] = "AWAITING_AUTODELETE"
        current = db.get_setting("auto_delete_seconds", "300")
        await query.edit_message_text(
            f"⏱ Current timer: <code>{current}s</code>\n\n"
            "Send the auto-delete timer in <b>seconds</b> (e.g. <code>300</code> for 5 minutes). "
            "Send <code>0</code> to disable auto-delete.",
            parse_mode="HTML", reply_markup=kb.cancel_kb(),
        )

    elif data == "toggle_protect":
        if not await _require_admin(query):
            return
        current = db.get_setting("protect_content", "0")
        new_val = "0" if current == "1" else "1"
        db.set_setting("protect_content", new_val)
        await query.answer(f"Content Protection is now {'ON' if new_val == '1' else 'OFF'}", show_alert=True)
        await query.edit_message_text(_settings_text(), reply_markup=kb.settings_menu_kb(), parse_mode="HTML")

    # ============================================================
    # Force-Sub Channels
    # ============================================================
    elif data == "admin_forcesub":
        if not await _require_admin(query):
            return
        channels = db.list_force_sub_channels()
        text = (
            "🔐 <b>Force Channel Subscription</b>\n\n"
            f"Currently mandatory: <code>{len(channels)}</code> channel(s)/group(s).\n\n"
            "• <b>Show Channels</b> — view the current list\n"
            "• <b>Add Channels</b> — add from where the bot is admin\n"
            "• <b>Remove Channels</b> — drop one that's no longer required"
        )
        await query.edit_message_text(text, reply_markup=kb.forcesub_menu_kb(), parse_mode="HTML")

    elif data == "fsub_show":
        if not await _require_admin(query):
            return
        channels = db.list_force_sub_channels()
        lines = [f"• <code>{cid}</code> — {title or 'Untitled'}" for cid, title, _link in channels] or [
            "<i>None configured — everyone can access files freely.</i>"
        ]
        text = "📄 <b>Force-Sub Channels</b>\n\n" + "\n".join(lines)
        await query.edit_message_text(text, reply_markup=kb.back_kb("admin_forcesub"), parse_mode="HTML")

    elif data == "fsub_add" or data.startswith("addfsubpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("addfsubpg_"):]) if data.startswith("addfsubpg_") else 0
        existing_ids = {cid for cid, _t, _l in db.list_force_sub_channels()}
        candidates = [c for c in db.list_admin_known_chats() if c[0] not in existing_ids]
        text = (
            "➕ <b>Add Force-Sub Channel</b>\n\nTap a channel/group the bot administers to make it mandatory:"
            if candidates else
            "➕ <b>Add Force-Sub Channel</b>\n\nNo new admin channels/groups detected. "
            "Add the bot as admin somewhere first, or enter one manually."
        )
        await query.edit_message_text(text, reply_markup=kb.forcesub_add_pick_kb(candidates, page), parse_mode="HTML")

    elif data == "fsub_add_manual":
        if not await _require_admin(query):
            return
        context.user_data["state"] = "AWAITING_ADD_FORCESUB_MANUAL"
        await query.edit_message_text(
            "🔐 Send the channel in the format:\n"
            "<code>channel_id | Channel Title | https://t.me/invitelink</code>\n\n"
            "The bot must be an <b>admin</b> in that channel to check membership.",
            parse_mode="HTML", reply_markup=kb.cancel_kb(),
        )

    elif data.startswith("addfsubpick_"):
        if not await _require_admin(query):
            return
        channel_id = int(data[len("addfsubpick_"):])
        chat = db.get_known_chat(channel_id)
        title = chat[1] if chat else str(channel_id)
        link = chat[3] if chat else ""
        db.add_force_sub_channel(channel_id, title, link)
        await query.answer(f"Added {title} to Force-Sub.", show_alert=True)
        existing_ids = {cid for cid, _t, _l in db.list_force_sub_channels()}
        candidates = [c for c in db.list_admin_known_chats() if c[0] not in existing_ids]
        text = "➕ <b>Add Force-Sub Channel</b>\n\nTap another to add, or go back:"
        await query.edit_message_text(text, reply_markup=kb.forcesub_add_pick_kb(candidates), parse_mode="HTML")

    elif data == "fsub_remove" or data.startswith("rmfsubpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("rmfsubpg_"):]) if data.startswith("rmfsubpg_") else 0
        channels = db.list_force_sub_channels()
        text = (
            "➖ <b>Remove Force-Sub Channel</b>\n\nTap one to remove it:"
            if channels else "➖ <b>Remove Force-Sub Channel</b>\n\nNothing configured yet."
        )
        await query.edit_message_text(text, reply_markup=kb.forcesub_remove_pick_kb(channels, page), parse_mode="HTML")

    elif data.startswith("rmfsub_"):
        if not await _require_admin(query):
            return
        channel_id = int(data[len("rmfsub_"):])
        db.remove_force_sub_channel(channel_id)
        await query.answer("Removed.", show_alert=True)
        channels = db.list_force_sub_channels()
        text = (
            "➖ <b>Remove Force-Sub Channel</b>\n\nTap one to remove it:"
            if channels else "➖ <b>Remove Force-Sub Channel</b>\n\nNothing left to remove."
        )
        await query.edit_message_text(text, reply_markup=kb.forcesub_remove_pick_kb(channels), parse_mode="HTML")

    # ============================================================
    # Users
    # ============================================================
    elif data == "admin_users":
        if not await _require_admin(query):
            return
        text = f"👥 <b>Manage Users</b>\n\nTracked: <code>{db.user_count()}</code>\nBanned: <code>{db.banned_count()}</code>"
        await query.edit_message_text(text, reply_markup=kb.users_menu_kb(), parse_mode="HTML")

    elif data == "list_users" or data.startswith("userlistpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("userlistpg_"):]) if data.startswith("userlistpg_") else 0
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
        await query.edit_message_text(text, reply_markup=kb.user_list_kb(len(users), page), parse_mode="HTML")

    elif data == "ban_user" or data.startswith("banpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("banpg_"):]) if data.startswith("banpg_") else 0
        users = db.list_bannable_users()
        text = "🚫 <b>Ban a User</b>\n\nTap a user to ban them:" if users else "🚫 <b>Ban a User</b>\n\nNo bannable users found."
        await query.edit_message_text(text, reply_markup=kb.ban_pick_kb(users, page), parse_mode="HTML")

    elif data.startswith("banpick_"):
        if not await _require_admin(query):
            return
        uid = int(data[len("banpick_"):])
        db.ban_user(uid)
        await query.answer(f"Banned {db.display_name(uid)}.", show_alert=True)
        users = db.list_bannable_users()
        text = "🚫 <b>Ban a User</b>\n\nTap another to ban, or go back:" if users else "🚫 <b>Ban a User</b>\n\nNo more bannable users."
        await query.edit_message_text(text, reply_markup=kb.ban_pick_kb(users), parse_mode="HTML")

    elif data == "unban_user" or data.startswith("unbanpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("unbanpg_"):]) if data.startswith("unbanpg_") else 0
        users = db.list_banned_users()
        text = "✅ <b>Unban a User</b>\n\nTap a user to unban them:" if users else "✅ <b>Unban a User</b>\n\nNo banned users."
        await query.edit_message_text(text, reply_markup=kb.unban_pick_kb(users, page), parse_mode="HTML")

    elif data.startswith("unbanpick_"):
        if not await _require_admin(query):
            return
        uid = int(data[len("unbanpick_"):])
        db.unban_user(uid)
        await query.answer(f"Unbanned {db.display_name(uid)}.", show_alert=True)
        users = db.list_banned_users()
        text = "✅ <b>Unban a User</b>\n\nTap another to unban, or go back:" if users else "✅ <b>Unban a User</b>\n\nNo banned users left."
        await query.edit_message_text(text, reply_markup=kb.unban_pick_kb(users), parse_mode="HTML")

    elif data == "export_users":
        if not await _require_admin(query):
            return
        rows = db.list_users_full()
        if not rows:
            await query.answer("No users to export!", show_alert=True)
            return
        path = "users_export.txt"
        with open(path, "w", encoding="utf-8") as f:
            for uid, fname, uname, banned in rows:
                name = fname or (("@" + uname) if uname else "Unknown")
                f.write(f"{name} | {uid} | {'Banned' if banned else 'Active'}\n")
        with open(path, "rb") as f:
            await query.message.reply_document(document=f, caption="📥 Exported Users (Name | ID | Status)")
        await query.edit_message_text("✅ Export complete!", reply_markup=kb.users_menu_kb(), parse_mode="HTML")

    # ============================================================
    # Admins
    # ============================================================
    elif data == "admin_admins":
        if not await _require_admin(query):
            return
        await query.edit_message_text(_admins_text(), reply_markup=kb.admins_menu_kb(), parse_mode="HTML")

    elif data == "add_admin" or data.startswith("addadminpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("addadminpg_"):]) if data.startswith("addadminpg_") else 0
        users = db.list_promotable_users()
        text = "➕ <b>Add Admin</b>\n\nTap a user to promote them:" if users else "➕ <b>Add Admin</b>\n\nNo eligible users found — they need to have messaged the bot first."
        await query.edit_message_text(text, reply_markup=kb.add_admin_pick_kb(users, page), parse_mode="HTML")

    elif data.startswith("addadminpick_"):
        if not await _require_admin(query):
            return
        uid = int(data[len("addadminpick_"):])
        db.add_admin(uid, added_by=user.id)
        await apply_admin_commands(context.bot, uid)
        await query.answer(f"{db.display_name(uid)} is now an admin.", show_alert=True)
        users = db.list_promotable_users()
        text = "➕ <b>Add Admin</b>\n\nTap another to promote, or go back:"
        await query.edit_message_text(text, reply_markup=kb.add_admin_pick_kb(users), parse_mode="HTML")

    elif data == "remove_admin" or data.startswith("rmadminpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("rmadminpg_"):]) if data.startswith("rmadminpg_") else 0
        admin_ids = db.list_admins()
        text = "➖ <b>Remove Admin</b>\n\nTap an admin to demote them:"
        await query.edit_message_text(
            text, reply_markup=kb.remove_admin_pick_kb(admin_ids, config.OWNER_ID, page), parse_mode="HTML"
        )

    elif data.startswith("rmadmin_"):
        if not await _require_admin(query):
            return
        target_id = int(data[len("rmadmin_"):])
        removed = db.remove_admin(target_id)
        if removed:
            await clear_admin_commands(context.bot, target_id)
            await query.answer(f"Removed admin {db.display_name(target_id)}", show_alert=True)
        else:
            await query.answer("The owner cannot be removed.", show_alert=True)
        admin_ids = db.list_admins()
        text = "➖ <b>Remove Admin</b>\n\nTap another to demote, or go back:"
        await query.edit_message_text(
            text, reply_markup=kb.remove_admin_pick_kb(admin_ids, config.OWNER_ID), parse_mode="HTML"
        )

    # ============================================================
    # Broadcast
    # ============================================================
    elif data == "admin_broadcast":
        if not await _require_admin(query):
            return
        context.user_data["state"] = "AWAITING_BROADCAST"
        await query.edit_message_text(
            "📢 <b>Broadcast</b>\n\nSend the message you want to broadcast to all tracked users.\n\n"
            "<i>Send /cancel to abort.</i>",
            parse_mode="HTML", reply_markup=kb.cancel_kb(),
        )

    # ============================================================
    # Files Management
    # ============================================================
    elif data == "admin_files":
        if not await _require_admin(query):
            return
        text = f"🗄 <b>Files Management</b>\n\nTotal files stored: <code>{db.file_count()}</code>"
        await query.edit_message_text(text, reply_markup=kb.files_menu_kb(), parse_mode="HTML")

    elif data == "file_getlink" or data.startswith("linkpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("linkpg_"):]) if data.startswith("linkpg_") else 0
        files = db.list_all_files()
        text = "🔗 <b>Get Link</b>\n\nTap a file to get its link:" if files else "🔗 <b>Get Link</b>\n\nNo files stored yet."
        await query.edit_message_text(text, reply_markup=kb.file_pick_kb(files, "linkpick_", "linkpg_", page), parse_mode="HTML")

    elif data.startswith("linkpick_"):
        if not await _require_admin(query):
            return
        file_id = data[len("linkpick_"):]
        row = db.get_file(file_id)
        if not row:
            await query.answer("File not found — it may have been removed.", show_alert=True)
            return
        link = f"https://t.me/{context.bot.username}?start={file_id}"
        name = row[4] or file_id
        text = f"🔗 <b>{name}</b>\n\n<code>{link}</code>"
        await query.edit_message_text(text, reply_markup=kb.back_kb("file_getlink"), parse_mode="HTML")

    elif data == "file_remove" or data.startswith("rmfilepg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("rmfilepg_"):]) if data.startswith("rmfilepg_") else 0
        files = db.list_all_files()
        text = "🗑 <b>Remove File</b>\n\nTap a file to remove it (deletes the link and the stored copy):" if files else "🗑 <b>Remove File</b>\n\nNo files stored yet."
        await query.edit_message_text(text, reply_markup=kb.file_pick_kb(files, "rmfilepick_", "rmfilepg_", page), parse_mode="HTML")

    elif data.startswith("rmfilepick_"):
        if not await _require_admin(query):
            return
        file_id = data[len("rmfilepick_"):]
        row = db.get_file(file_id)
        if row:
            storage_channel_id = db.get_setting("storage_channel_id")
            if storage_channel_id:
                try:
                    await context.bot.delete_message(chat_id=int(storage_channel_id), message_id=row[1])
                except Exception:
                    pass  # already gone from the channel — DB cleanup still proceeds
            db.delete_file(file_id)
            await query.answer(f"Removed {row[4] or file_id}.", show_alert=True)
        else:
            await query.answer("Already removed.", show_alert=True)
        files = db.list_all_files()
        text = "🗑 <b>Remove File</b>\n\nTap another to remove, or go back:" if files else "🗑 <b>Remove File</b>\n\nNo files left."
        await query.edit_message_text(text, reply_markup=kb.file_pick_kb(files, "rmfilepick_", "rmfilepg_"), parse_mode="HTML")

    elif data == "file_changeid" or data.startswith("chidpg_"):
        if not await _require_admin(query):
            return
        page = int(data[len("chidpg_"):]) if data.startswith("chidpg_") else 0
        files = db.list_all_files()
        text = "🆔 <b>Change File ID</b>\n\nTap a file to issue it a new link (the old link stops working):" if files else "🆔 <b>Change File ID</b>\n\nNo files stored yet."
        await query.edit_message_text(text, reply_markup=kb.file_pick_kb(files, "chidpick_", "chidpg_", page), parse_mode="HTML")

    elif data.startswith("chidpick_"):
        if not await _require_admin(query):
            return
        old_file_id = data[len("chidpick_"):]
        new_id = db.regenerate_file_id(old_file_id)
        if not new_id:
            await query.answer("File not found — it may have been removed.", show_alert=True)
            return
        row = db.get_file(new_id)
        name = row[4] or new_id
        link = f"https://t.me/{context.bot.username}?start={new_id}"
        text = f"🆔 <b>New link issued for {name}</b>\n\n<code>{link}</code>\n\n<i>The old link no longer works.</i>"
        await query.edit_message_text(text, reply_markup=kb.back_kb("admin_files"), parse_mode="HTML")

    # ============================================================
    # Cancel
    # ============================================================
    elif data == "cancel_action":
        context.user_data.pop("state", None)
        if db.is_admin(user.id):
            await query.edit_message_text("✅ Action cancelled.", reply_markup=kb.admin_main_kb(), parse_mode="HTML")
        else:
            await query.edit_message_text("✅ Cancelled.", reply_markup=kb.main_menu_kb(user.id), parse_mode="HTML")

    # ============================================================
    # File subscription re-check
    # ============================================================
    elif data.startswith("check_sub_"):
        file_id = data[len("check_sub_"):]
        if await is_user_subscribed(context, user.id):
            await query.edit_message_text("✅ Access granted! Fetching...", parse_mode="HTML")
            await deliver_file(context, query, user.id, file_id, edit_status=True)
        else:
            await query.answer("❌ You haven't joined yet. Join then tap Check Again.", show_alert=True)


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


def _admins_text() -> str:
    admin_ids = db.list_admins()
    lines = []
    for aid in admin_ids:
        role = "👑 Owner" if db.is_owner(aid) else "🛡 Admin"
        lines.append(f"{role}: {db.display_name(aid)} (<code>{aid}</code>)")
    return "🛡 <b>Manage Admins</b>\n\n" + "\n".join(lines)
