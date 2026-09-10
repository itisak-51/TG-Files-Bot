"""
Registry of every user-facing text string that admins can edit live from
Settings -> Edit Mode, instead of it being hardcoded in Python.

Each entry: key -> (short label shown in the Edit Mode picker, default text).
Actual values are stored in the settings table under "text_<key>" the first
time they're changed; until then, db.get_text(key) falls back to the
default here.

Placeholders (only where noted) are filled in with str.format() at the
call site — don't remove them when editing, or that piece of info won't
show up anymore.
"""

EDITABLE_TEXTS = {
    "welcome": (
        "👋 Welcome Message",
        "👋 Hey {name}!\n\nWelcome to Premium File Store 📂\nI store files securely and hand out shareable links.\n\n👇 Use the menu below to get started.",
    ),
    "help": (
        "❓ Help Text",
        "❓ <b>How This Bot Works</b>\n\n"
        "1️⃣ Open a file link that was shared with you.\n"
        "2️⃣ Join the required channel(s)/group(s) if asked.\n"
        "3️⃣ I'll deliver your file — it auto-deletes after a timer, so save it right away.",
    ),
    "about": (
        "ℹ️ About Text",
        "ℹ️ <b>About This Bot</b>\n\nA secure file-store &amp; delivery bot with force-subscribe gating "
        "and automatic copyright-safe deletion.",
    ),
    "forcesub_prompt": (
        "⚠️ Force-Sub Prompt",
        "⚠️ <b>You haven't joined these channel(s)/group(s) yet:</b>\n\nJoin them below, then tap <b>I Joined, Check Again</b>.",
    ),
    "fetching": (
        "⏳ Fetching Status",
        "⏳ <b>Fetching your file from the secure vault...</b>",
    ),
    "delivered": (
        "✅ Delivered Status",
        "✅ <b>Success!</b> Your file is above.",
    ),
    "brand_label": (
        "🏷 Brand Label (above each delivered file, blank = off)",
        "",
    ),
    "no_forward_warning": (
        "⚠️ No-Forward Warning (shown only when Content Protection is OFF)",
        "⚠️ Forward this file anywhere else. It will be deleted once the timer ends.",
    ),
    "auto_deleted": (
        "🗑 Auto-Delete Notice",
        "Files have been deleted for some reason.",
    ),
    "upload_blocked": (
        "⛔ Upload-Blocked (shown to non-admins who send a file)",
        "📥 This bot delivers files via shared links only — uploading isn't available here. "
        "If someone sent you a link, tap it (or send it to me as /start &lt;code&gt;) to get your file.",
    ),
    "banned_notice": (
        "⛔ Banned Notice",
        "⛔ You are banned from using this bot.",
    ),
}


def default_text(key: str) -> str:
    return EDITABLE_TEXTS.get(key, ("", ""))[1]
