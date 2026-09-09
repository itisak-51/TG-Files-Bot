"""
All inline keyboards live here so the "look" of the bot can be tweaked
in one place without touching handler logic.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db

PAGE_SIZE = 8


def _paginated_kb(items, pick_prefix: str, page_prefix: str, page: int, back_target: str,
                   page_size: int = PAGE_SIZE, extra_rows=None):
    """items: list of (id, label) tuples. Renders one button per item plus
    Prev/Next nav and a Back button. Used for every 'pick a user / pick a
    channel / pick a file' menu in the admin panel."""
    start = page * page_size
    chunk = items[start:start + page_size]
    rows = list(extra_rows) if extra_rows else []
    for item_id, label in chunk:
        rows.append([InlineKeyboardButton(label, callback_data=f"{pick_prefix}{item_id}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{page_prefix}{page - 1}"))
    if start + page_size < len(items):
        nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"{page_prefix}{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=back_target)])
    return InlineKeyboardMarkup(rows)


def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]])


def back_kb(target: str, label: str = "🔙 Back"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=target)]])


def main_menu_kb(user_id: int):
    rows = [
        [InlineKeyboardButton("📤 Upload File", callback_data="menu_upload")],
        [InlineKeyboardButton("ℹ️ About", callback_data="menu_about"),
         InlineKeyboardButton("❓ Help", callback_data="menu_help")],
    ]
    if db.is_admin(user_id):
        rows.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin_main")])
    return InlineKeyboardMarkup(rows)


def admin_main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
         InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("👥 Users", callback_data="admin_users"),
         InlineKeyboardButton("🛡 Admins", callback_data="admin_admins")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🗄 Files Management", callback_data="admin_files")],
        [InlineKeyboardButton("🏠 Back to Home", callback_data="home")],
    ])


# ---------------- Settings ----------------

def settings_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 Storage Channel", callback_data="set_storage")],
        [InlineKeyboardButton("✍️ Welcome Message", callback_data="set_welcome")],
        [InlineKeyboardButton("⏱ Auto-Delete Timer", callback_data="set_autodelete")],
        [InlineKeyboardButton("🛡 Toggle Content Protection", callback_data="toggle_protect")],
        [InlineKeyboardButton("🔐 Force Channel Subscription", callback_data="admin_forcesub")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")],
    ])


def storage_pick_kb(channels, page: int = 0):
    """channels: list of (chat_id, title, chat_type, invite_link) the bot
    administers. Falls back to a manual-entry button when none are known
    yet (e.g. bot was made admin before tracking started)."""
    items = [(cid, f"{'📢' if ctype == 'channel' else '👥'} {title}") for cid, title, ctype, _link in channels]
    extra = [[InlineKeyboardButton("✍️ Enter Manually / Forward a Message", callback_data="set_storage_manual")]]
    return _paginated_kb(items, "stopick_", "stopg_", page, "admin_settings", extra_rows=extra)


def welcome_edit_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Edit Welcome Message", callback_data="set_welcome")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ])


# ---------------- Users ----------------

def users_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 List Users", callback_data="list_users")],
        [InlineKeyboardButton("🚫 Ban Users", callback_data="ban_user"),
         InlineKeyboardButton("✅ Unban Users", callback_data="unban_user")],
        [InlineKeyboardButton("📥 Export Users List", callback_data="export_users")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")],
    ])


def user_list_kb(total_items: int, page: int, page_size: int = PAGE_SIZE):
    """Read-only paginated view (no per-row pick action) — the message body
    already contains the rendered text lines for this page; here we just
    need Prev / Next / Back."""
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"userlistpg_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"userlistpg_{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="admin_users")])
    return InlineKeyboardMarkup(rows)


def ban_pick_kb(users, page: int = 0):
    return _paginated_kb(users, "banpick_", "banpg_", page, "admin_users")


def unban_pick_kb(users, page: int = 0):
    return _paginated_kb(users, "unbanpick_", "unbanpg_", page, "admin_users")


# ---------------- Admins ----------------

def admins_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Admin", callback_data="add_admin"),
         InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")],
    ])


def add_admin_pick_kb(users, page: int = 0):
    return _paginated_kb(users, "addadminpick_", "addadminpg_", page, "admin_admins")


def remove_admin_pick_kb(admin_ids, owner_id, page: int = 0):
    items = [(aid, f"➖ {db.display_name(aid)} ({aid})") for aid in admin_ids if aid != owner_id]
    return _paginated_kb(items, "rmadmin_", "rmadminpg_", page, "admin_admins")


# ---------------- Force-Sub Channels ----------------

def forcesub_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Show Channels", callback_data="fsub_show")],
        [InlineKeyboardButton("➕ Add Channels", callback_data="fsub_add")],
        [InlineKeyboardButton("➖ Remove Channels", callback_data="fsub_remove")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin_settings")],
    ])


def forcesub_add_pick_kb(candidates, page: int = 0):
    """candidates: list of (chat_id, title, chat_type, invite_link) — bot-admin
    chats not yet configured as force-sub."""
    items = [(cid, f"➕ {'📢' if ctype == 'channel' else '👥'} {title}") for cid, title, ctype, _link in candidates]
    extra = [[InlineKeyboardButton("✍️ Enter Manually", callback_data="fsub_add_manual")]]
    return _paginated_kb(items, "addfsubpick_", "addfsubpg_", page, "admin_forcesub", extra_rows=extra)


def forcesub_remove_pick_kb(channels, page: int = 0):
    items = [(cid, f"➖ {title or cid}") for cid, title, _link in channels]
    return _paginated_kb(items, "rmfsub_", "rmfsubpg_", page, "admin_forcesub")


# ---------------- Files ----------------

def files_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Get Link", callback_data="file_getlink")],
        [InlineKeyboardButton("🗑 Remove File", callback_data="file_remove")],
        [InlineKeyboardButton("🆔 Change File ID", callback_data="file_changeid")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_main")],
    ])


def file_pick_kb(files, pick_prefix: str, page_prefix: str, page: int = 0):
    """files: list of (file_id, file_type, file_name, uploaded_at)."""
    icons = {"document": "📄", "video": "🎬", "photo": "🖼", "audio": "🎵",
             "animation": "🎞", "voice": "🎤", "video_note": "⭕", "sticker": "🧩"}
    items = [
        (fid, f"{icons.get(ftype, '📁')} {fname or fid}")
        for fid, ftype, fname, _ts in files
    ]
    return _paginated_kb(items, pick_prefix, page_prefix, page, "admin_files")


def confirm_kb(confirm_data: str, cancel_data: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ YES, CONFIRM", callback_data=confirm_data)],
        [InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)],
    ])


def force_sub_kb(channels, file_id: str):
    rows = []
    for _channel_id, title, link in channels:
        if link:
            rows.append([InlineKeyboardButton(f"🔗 Join {title or 'Channel'}", url=link)])
    rows.append([InlineKeyboardButton("✅ I Joined, Check Again", callback_data=f"check_sub_{file_id}")])
    return InlineKeyboardMarkup(rows)


def home_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]])
