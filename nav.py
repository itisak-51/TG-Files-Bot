"""
The bottom-of-screen persistent keyboard (ReplyKeyboardMarkup) that admins
navigate the bot with. Regular users never see this — they're a pure
file-receive experience.

Design: bottom buttons handle NAVIGATION between menu levels (Root -> Admin
Panel -> Settings -> Force-Sub, etc.) and simple one-tap toggles/actions.
Anything that needs a dynamic pick from a list (a specific user, channel,
or file) or a free-text prompt still uses an inline keyboard attached to
its own message, layered on top of whatever the bottom keyboard currently
shows — the two systems don't conflict since Telegram tracks them
separately.

Every level knows its own parent, so "🔙 Back" always resolves correctly
regardless of how deep the admin has navigated.
"""
from telegram import ReplyKeyboardMarkup

BACK = "🔙 Back"

LEVEL_PARENT = {
    "admin": "root",
    "settings": "admin",
    "forcesub": "settings",
    "users": "admin",
    "admins": "admin",
    "files": "admin",
    "backup": "admin",
}

LEVEL_BUTTONS = {
    "root": [
        ["📤 Upload File"],
        ["🛠 Admin Panel"],
        ["❓ Help", "ℹ️ About"],
    ],
    "admin": [
        ["📊 Statistics", "⚙️ Settings"],
        ["👥 Users", "🛡 Admins"],
        ["📢 Broadcast", "🗄 Files Management"],
        ["💾 Backup"],
        [BACK],
    ],
    "settings": [
        ["🔒 Storage Channel", "✍️ Welcome Message"],
        ["⏱ Auto-Delete Timer", "🛡 Toggle Content Protection"],
        ["🔐 Force Channel Subscription", "🎛 Edit Mode"],
        [BACK],
    ],
    "forcesub": [
        ["📄 Show Channels"],
        ["➕ Add Channels", "➖ Remove Channels"],
        [BACK],
    ],
    "users": [
        ["📋 List Users"],
        ["🚫 Ban Users", "✅ Unban Users"],
        ["📥 Export Users List"],
        [BACK],
    ],
    "admins": [
        ["➕ Add Admin", "➖ Remove Admin"],
        [BACK],
    ],
    "files": [
        ["🔗 Get Link", "🗑 Remove File"],
        ["🆔 Change File ID"],
        [BACK],
    ],
    "backup": [
        ["💾 Backup Data", "♻️ Restore Data"],
        ["🔥 Destroy Data"],
        [BACK],
    ],
}

LEVEL_ARRIVAL_TEXT = {
    "root": "🏠 <b>Main Menu</b>",
    "admin": "🛠 <b>Admin Panel</b>\n\nManage your bot live — no restarts needed.",
    "settings": "⚙️ <b>Settings</b>\n\nPick what to configure below.",
    "forcesub": "🔐 <b>Force Channel Subscription</b>\n\nShow, add, or remove mandatory channels/groups.",
    "users": "👥 <b>Manage Users</b>",
    "admins": "🛡 <b>Manage Admins</b>",
    "files": "🗄 <b>Files Management</b>",
    "backup": "💾 <b>Backup &amp; Restore</b>\n\nYour local data (metadata + config only — not the files themselves, those stay on Telegram) can be backed up and restored here.",
}


def reply_kb(level: str) -> ReplyKeyboardMarkup:
    rows = LEVEL_BUTTONS.get(level, LEVEL_BUTTONS["root"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def all_button_labels() -> set:
    labels = set()
    for rows in LEVEL_BUTTONS.values():
        for row in rows:
            labels.update(row)
    return labels
