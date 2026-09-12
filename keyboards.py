"""
Inline keyboards — used for dynamic pick-lists (choose a specific user,
channel, or file), quick toggles/confirmations, and free-text-prompt
cancel buttons. Menu *navigation* (Root/Admin/Settings/etc.) lives in the
persistent bottom keyboard instead — see nav.py.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database as db

PAGE_SIZE = 8


def _paginated_kb(items, pick_prefix: str, page_prefix: str, page: int, back_target: str,
                   page_size: int = PAGE_SIZE, extra_rows=None):
    """items: list of (id, label) tuples. Renders one button per item plus
    Prev/Next nav and a Back button."""
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
    if back_target:
        rows.append([InlineKeyboardButton("🔙 Back", callback_data=back_target)])
    return InlineKeyboardMarkup(rows)


def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]])


def back_kb(target: str, label: str = "🔙 Back"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=target)]])


def confirm_kb(confirm_data: str, cancel_data: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ YES, CONFIRM", callback_data=confirm_data)],
        [InlineKeyboardButton("❌ Cancel", callback_data=cancel_data)],
    ])


# ---------------- DevUploads ----------------

def devuploads_files_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 List (Live from DevUploads)", callback_data="devfiles_list")],
        [InlineKeyboardButton("✏️ Rename a Mirrored File", callback_data="devfiles_rename")],
        [InlineKeyboardButton("🗑 Delete a Mirrored File", callback_data="devfiles_delete")],
    ])


def devuploads_folders_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 List Folders", callback_data="devfolders_list")],
        [InlineKeyboardButton("➕ Create Folder", callback_data="devfolders_create")],
        [InlineKeyboardButton("🗑 Delete a Folder", callback_data="devfolders_delete")],
    ])


def devuploads_file_pick_kb(files, pick_prefix: str, page_prefix: str, page: int = 0):
    """files: list of (file_id, file_name, devuploads_code) — our own
    tracked files that have a DevUploads mirror."""
    items = [(fid, f"📄 {fname or fid}") for fid, fname, _code in files]
    return _paginated_kb(items, pick_prefix, page_prefix, page, None)


# ---------------- Storage / Force-Sub channel pickers ----------------

def storage_pick_kb(channels, page: int = 0):
    """channels: list of (chat_id, title, chat_type, invite_link) the bot
    currently administers (live-verified). Always offers manual entry and a
    refresh, since Telegram gives no way to auto-discover every chat a bot
    is already in — only chats it's *told about* (by event or by hand)."""
    items = [(cid, f"{'📢' if ctype == 'channel' else '👥'} {title}") for cid, title, ctype, _link in channels]
    extra = [
        [InlineKeyboardButton("✍️ Enter Manually / Forward a Message", callback_data="set_storage_manual")],
        [InlineKeyboardButton("🔄 Refresh Detected Channels", callback_data="storage_refresh")],
    ]
    return _paginated_kb(items, "stopick_", "stopg_", page, None, extra_rows=extra)


def welcome_edit_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Edit Welcome Message", callback_data="set_welcome")]])


def ban_pick_kb(users, page: int = 0):
    return _paginated_kb(users, "banpick_", "banpg_", page, None)


def unban_pick_kb(users, page: int = 0):
    return _paginated_kb(users, "unbanpick_", "unbanpg_", page, None)


def add_admin_pick_kb(users, page: int = 0):
    return _paginated_kb(users, "addadminpick_", "addadminpg_", page, None)


def remove_admin_pick_kb(admin_ids, owner_id, page: int = 0):
    items = [(aid, f"➖ {db.display_name(aid)} ({aid})") for aid in admin_ids if aid != owner_id]
    return _paginated_kb(items, "rmadmin_", "rmadminpg_", page, None)


def forcesub_add_pick_kb(candidates, page: int = 0):
    """candidates: list of (chat_id, title, chat_type, invite_link) — bot-admin
    chats not yet configured as force-sub."""
    items = [(cid, f"➕ {'📢' if ctype == 'channel' else '👥'} {title}") for cid, title, ctype, _link in candidates]
    extra = [
        [InlineKeyboardButton("✍️ Enter Manually", callback_data="fsub_add_manual")],
        [InlineKeyboardButton("🔄 Refresh Detected Channels", callback_data="fsub_add_refresh")],
    ]
    return _paginated_kb(items, "addfsubpick_", "addfsubpg_", page, None, extra_rows=extra)


def forcesub_remove_pick_kb(channels, page: int = 0):
    items = [(cid, f"➖ {title or cid}") for cid, title, _link in channels]
    return _paginated_kb(items, "rmfsub_", "rmfsubpg_", page, None)


# ---------------- Users ----------------

def user_list_kb(total_items: int, page: int, page_size: int = PAGE_SIZE):
    """Read-only paginated view — the message body already contains the
    rendered text lines for this page; here we just need Prev / Next."""
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"userlistpg_{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"userlistpg_{page + 1}"))
    return InlineKeyboardMarkup([nav]) if nav else None


# ---------------- Files ----------------

def file_pick_kb(files, pick_prefix: str, page_prefix: str, page: int = 0):
    """files: list of (file_id, file_type, file_name, uploaded_at)."""
    icons = {"document": "📄", "video": "🎬", "photo": "🖼", "audio": "🎵",
             "animation": "🎞", "voice": "🎤", "video_note": "⭕", "sticker": "🧩"}
    items = [
        (fid, f"{icons.get(ftype, '📁')} {fname or fid}")
        for fid, ftype, fname, _ts in files
    ]
    return _paginated_kb(items, pick_prefix, page_prefix, page, None)


# ---------------- Edit Mode ----------------

def edit_mode_pick_kb():
    import texts
    rows = [[InlineKeyboardButton(label, callback_data=f"edittext_{key}")]
            for key, (label, _default) in texts.EDITABLE_TEXTS.items()]
    return InlineKeyboardMarkup(rows)


# ---------------- Force-sub gate (shown to end users) ----------------

def force_sub_kb(channels, continue_data: str):
    """channels: only the ones the user HASN'T joined yet — never the full
    configured list, so the prompt always reflects what's actually left."""
    rows = []
    for _channel_id, title, link in channels:
        if link:
            rows.append([InlineKeyboardButton(f"🔗 Join {title or 'Channel'}", url=link)])
    rows.append([InlineKeyboardButton("✅ I Joined, Check Again", callback_data=continue_data)])
    return InlineKeyboardMarkup(rows)


def home_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]])
