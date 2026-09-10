"""
SQLite persistence layer.

Why SQLite instead of the original raw JSON files:
- Atomic writes (no half-written files if the process is killed mid-save)
- No "read whole file into RAM, mutate, write whole file back" on every action
- Safe under concurrent handlers (WAL mode)
- Trivial to back up: it's one file
"""
import os
import secrets
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager

import config

_lock = threading.Lock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL;")
_conn.row_factory = sqlite3.Row


@contextmanager
def _cursor():
    with _lock:
        cur = _conn.cursor()
        try:
            yield cur
            _conn.commit()
        finally:
            cur.close()


def _ensure_column(cur, table: str, column: str, coltype: str):
    """Idempotent 'ALTER TABLE ADD COLUMN' for upgrading DBs created by older
    versions of this bot without needing a migration tool."""
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db():
    with _cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_seen INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS banned (
            user_id INTEGER PRIMARY KEY,
            banned_at INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS force_sub_channels (
            channel_id INTEGER PRIMARY KEY,
            title TEXT,
            invite_link TEXT
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            channel_msg_id INTEGER,
            uploader_id INTEGER,
            file_type TEXT,
            uploaded_at INTEGER
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        # Every chat (group/channel) the bot has ever seen via my_chat_member
        # updates, and whether it currently holds admin rights there. This is
        # what lets the admin panel offer "pick a channel" menus instead of
        # requiring admins to hunt down and paste raw chat IDs.
        cur.execute("""CREATE TABLE IF NOT EXISTS known_chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            chat_type TEXT,
            is_admin INTEGER DEFAULT 0,
            invite_link TEXT,
            updated_at INTEGER
        )""")

        # ---- Upgrade older DBs in place ----
        _ensure_column(cur, "users", "first_name", "TEXT")
        _ensure_column(cur, "users", "username", "TEXT")
        _ensure_column(cur, "files", "file_name", "TEXT")
        _ensure_column(cur, "files", "caption", "TEXT")

        # Seed owner as permanent admin
        cur.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (config.OWNER_ID, config.OWNER_ID, int(time.time())),
        )
        # Seed default settings if not present
        defaults = {
            "auto_delete_seconds": str(config.DEFAULT_AUTO_DELETE_SECONDS),
            "protect_content": config.DEFAULT_PROTECT_CONTENT,
            "storage_channel_id": "",
        }
        for k, v in defaults.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        # Migrate the old single hardcoded welcome_msg setting (pre Edit-Mode) into
        # the generic editable-text store, if present and not already migrated.
        legacy_welcome = cur.execute("SELECT value FROM settings WHERE key='welcome_msg'").fetchone()
        has_new_welcome = cur.execute("SELECT 1 FROM settings WHERE key='text_welcome'").fetchone()
        if legacy_welcome and not has_new_welcome:
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('text_welcome', ?)", (legacy_welcome[0],))

        # Seed every editable text with its default if it has no value yet
        import texts as _texts
        for key, (_label, default_val) in _texts.EDITABLE_TEXTS.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (f"text_{key}", default_val))


# ---------------- Users ----------------

def track_user(user_id: int, first_name: str = "", username: str = ""):
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO users (user_id, first_seen, first_name, username) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET first_name=excluded.first_name, username=excluded.username",
            (user_id, int(time.time()), first_name or "", username or ""),
        )


def user_count() -> int:
    with _cursor() as cur:
        return cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def all_user_ids() -> list:
    with _cursor() as cur:
        return [r[0] for r in cur.execute("SELECT user_id FROM users").fetchall()]


def list_users_full() -> list:
    """Every tracked user with name + ban status, oldest first. Row =
    (user_id, first_name, username, is_banned)."""
    with _cursor() as cur:
        return cur.execute(
            "SELECT u.user_id, u.first_name, u.username, "
            "CASE WHEN b.user_id IS NULL THEN 0 ELSE 1 END AS is_banned "
            "FROM users u LEFT JOIN banned b ON u.user_id = b.user_id "
            "ORDER BY u.first_seen"
        ).fetchall()


def display_name(user_id: int) -> str:
    """Best-effort human-readable label for a user_id: first name, else
    @username, else the raw ID."""
    with _cursor() as cur:
        row = cur.execute("SELECT first_name, username FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return str(user_id)
    first_name, username = row
    if first_name:
        return first_name
    if username:
        return "@" + username
    return str(user_id)


# ---------------- Bans ----------------

def is_banned(user_id: int) -> bool:
    with _cursor() as cur:
        return cur.execute("SELECT 1 FROM banned WHERE user_id=?", (user_id,)).fetchone() is not None


def ban_user(user_id: int):
    with _cursor() as cur:
        cur.execute("INSERT OR REPLACE INTO banned (user_id, banned_at) VALUES (?, ?)", (user_id, int(time.time())))


def unban_user(user_id: int):
    with _cursor() as cur:
        cur.execute("DELETE FROM banned WHERE user_id=?", (user_id,))


def banned_count() -> int:
    with _cursor() as cur:
        return cur.execute("SELECT COUNT(*) FROM banned").fetchone()[0]


def list_bannable_users() -> list:
    """Tracked users who are not banned and not admins/owner — the pool
    shown in the 'Ban User' picker. Row = (user_id, label)."""
    with _cursor() as cur:
        rows = cur.execute(
            "SELECT u.user_id, u.first_name, u.username FROM users u "
            "WHERE u.user_id NOT IN (SELECT user_id FROM banned) "
            "AND u.user_id NOT IN (SELECT user_id FROM admins) "
            "ORDER BY u.first_seen DESC"
        ).fetchall()
    return [(r[0], _label(r[0], r[1], r[2])) for r in rows]


def list_banned_users() -> list:
    """Row = (user_id, label)."""
    with _cursor() as cur:
        rows = cur.execute(
            "SELECT b.user_id, u.first_name, u.username FROM banned b "
            "LEFT JOIN users u ON u.user_id = b.user_id ORDER BY b.banned_at DESC"
        ).fetchall()
    return [(r[0], _label(r[0], r[1], r[2])) for r in rows]


def _label(user_id, first_name, username) -> str:
    if first_name:
        return f"{first_name} ({user_id})"
    if username:
        return f"@{username} ({user_id})"
    return str(user_id)


# ---------------- Admins ----------------

def is_admin(user_id: int) -> bool:
    if user_id == config.OWNER_ID:
        return True
    with _cursor() as cur:
        return cur.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone() is not None


def is_owner(user_id: int) -> bool:
    return user_id == config.OWNER_ID


def add_admin(user_id: int, added_by: int):
    with _cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (user_id, added_by, int(time.time())),
        )


def remove_admin(user_id: int) -> bool:
    if user_id == config.OWNER_ID:
        return False  # owner can never be removed
    with _cursor() as cur:
        cur.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    return True


def list_admins() -> list:
    with _cursor() as cur:
        return [r[0] for r in cur.execute("SELECT user_id FROM admins ORDER BY added_at").fetchall()]


def list_promotable_users() -> list:
    """Tracked users who are not already admins — the pool shown in the
    'Add Admin' picker. Row = (user_id, label)."""
    with _cursor() as cur:
        rows = cur.execute(
            "SELECT u.user_id, u.first_name, u.username FROM users u "
            "WHERE u.user_id NOT IN (SELECT user_id FROM admins) "
            "ORDER BY u.first_seen DESC"
        ).fetchall()
    return [(r[0], _label(r[0], r[1], r[2])) for r in rows]


# ---------------- Force-Sub Channels ----------------

def add_force_sub_channel(channel_id: int, title: str, invite_link: str):
    with _cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO force_sub_channels (channel_id, title, invite_link) VALUES (?, ?, ?)",
            (channel_id, title, invite_link),
        )


def remove_force_sub_channel(channel_id: int):
    with _cursor() as cur:
        cur.execute("DELETE FROM force_sub_channels WHERE channel_id=?", (channel_id,))


def list_force_sub_channels() -> list:
    with _cursor() as cur:
        return cur.execute("SELECT channel_id, title, invite_link FROM force_sub_channels").fetchall()


def is_force_sub_channel(channel_id: int) -> bool:
    with _cursor() as cur:
        return cur.execute(
            "SELECT 1 FROM force_sub_channels WHERE channel_id=?", (channel_id,)
        ).fetchone() is not None


# ---------------- Known chats (bot membership tracking) ----------------

def upsert_known_chat(chat_id: int, title: str, chat_type: str, is_admin_here: bool, invite_link: str):
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO known_chats (chat_id, title, chat_type, is_admin, invite_link, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, chat_type=excluded.chat_type, "
            "is_admin=excluded.is_admin, invite_link=excluded.invite_link, updated_at=excluded.updated_at",
            (chat_id, title, chat_type, 1 if is_admin_here else 0, invite_link, int(time.time())),
        )


def list_admin_known_chats() -> list:
    """Every group/channel the bot currently has admin rights in.
    Row = (chat_id, title, chat_type, invite_link)."""
    with _cursor() as cur:
        return cur.execute(
            "SELECT chat_id, title, chat_type, invite_link FROM known_chats WHERE is_admin=1 ORDER BY title"
        ).fetchall()


def get_known_chat(chat_id: int):
    with _cursor() as cur:
        return cur.execute(
            "SELECT chat_id, title, chat_type, invite_link FROM known_chats WHERE chat_id=?", (chat_id,)
        ).fetchone()


# ---------------- Files ----------------

def add_file(file_id: str, channel_msg_id: int, uploader_id: int, file_type: str,
             file_name: str = "", caption: str = ""):
    with _cursor() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO files "
            "(file_id, channel_msg_id, uploader_id, file_type, file_name, caption, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (file_id, channel_msg_id, uploader_id, file_type, file_name, caption, int(time.time())),
        )


def get_file(file_id: str):
    with _cursor() as cur:
        return cur.execute(
            "SELECT file_id, channel_msg_id, uploader_id, file_type, file_name, caption, uploaded_at "
            "FROM files WHERE file_id=?",
            (file_id,),
        ).fetchone()


def delete_file(file_id: str) -> bool:
    with _cursor() as cur:
        cur.execute("DELETE FROM files WHERE file_id=?", (file_id,))
        return cur.rowcount > 0


def regenerate_file_id(old_file_id: str):
    """Issues a brand-new share link for the same stored file, and retires
    the old one (its link stops working). Returns the new file_id, or None
    if old_file_id doesn't exist."""
    with _cursor() as cur:
        row = cur.execute(
            "SELECT channel_msg_id, uploader_id, file_type, file_name, caption FROM files WHERE file_id=?",
            (old_file_id,),
        ).fetchone()
        if not row:
            return None
        channel_msg_id, uploader_id, file_type, file_name, caption = row
        new_id = f"{channel_msg_id}{secrets.token_hex(3)}"
        cur.execute("DELETE FROM files WHERE file_id=?", (old_file_id,))
        cur.execute(
            "INSERT INTO files (file_id, channel_msg_id, uploader_id, file_type, file_name, caption, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_id, channel_msg_id, uploader_id, file_type, file_name, caption, int(time.time())),
        )
        return new_id


def clear_files():
    with _cursor() as cur:
        cur.execute("DELETE FROM files")


def file_count() -> int:
    with _cursor() as cur:
        return cur.execute("SELECT COUNT(*) FROM files").fetchone()[0]


def list_all_files() -> list:
    """Row = (file_id, file_type, file_name, uploaded_at), newest first."""
    with _cursor() as cur:
        return cur.execute(
            "SELECT file_id, file_type, file_name, uploaded_at FROM files ORDER BY uploaded_at DESC"
        ).fetchall()


def recent_files(limit: int = 10) -> list:
    with _cursor() as cur:
        return cur.execute(
            "SELECT file_id, file_type, uploaded_at FROM files ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


# ---------------- Settings (key/value store) ----------------

def get_setting(key: str, default: str = "") -> str:
    with _cursor() as cur:
        row = cur.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str):
    with _cursor() as cur:
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ---------------- Editable texts (Settings -> Edit Mode) ----------------

def get_text(key: str) -> str:
    import texts as _texts
    return get_setting(f"text_{key}", _texts.default_text(key))


def set_text(key: str, value: str):
    set_setting(f"text_{key}", value)


# ---------------- Known chats: full listing for live re-verification ----------------

def all_known_chat_ids() -> list:
    with _cursor() as cur:
        return [r[0] for r in cur.execute("SELECT chat_id FROM known_chats").fetchall()]


# ---------------- Backup / Restore / Destroy ----------------
# Everything this bot stores locally is metadata + pointers (which channel a
# file lives in, whose files those are, which channels are mandatory, which
# settings are configured) — never the file bytes themselves, since those
# stay on Telegram inside the storage channel. Backing up this DB is
# therefore a complete, self-contained snapshot of "where everything is and
# how the bot is configured."

REQUIRED_BACKUP_TABLES = (
    "users", "admins", "banned", "files", "settings", "force_sub_channels", "known_chats",
)


def create_backup(dest_path: str):
    """Writes a consistent point-in-time snapshot of the whole DB to dest_path."""
    with _lock:
        dest = sqlite3.connect(dest_path)
        try:
            _conn.backup(dest)
        finally:
            dest.close()


def is_valid_backup_file(path: str) -> bool:
    try:
        test = sqlite3.connect(path)
        try:
            tables = {r[0] for r in test.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        finally:
            test.close()
        return all(t in tables for t in REQUIRED_BACKUP_TABLES)
    except Exception:
        return False


def restore_from(path: str) -> bool:
    """Swaps the live DB for the one at `path`. A safety copy of the DB being
    replaced is kept alongside it (config.DB_PATH + '.before_restore') in
    case something goes wrong. Returns False (no changes made) if `path`
    doesn't look like a bot backup."""
    global _conn
    if not is_valid_backup_file(path):
        return False
    with _lock:
        _conn.close()
        for suffix in ("-wal", "-shm"):
            try:
                os.remove(config.DB_PATH + suffix)
            except FileNotFoundError:
                pass
        try:
            shutil.copy2(config.DB_PATH, config.DB_PATH + ".before_restore")
        except FileNotFoundError:
            pass
        shutil.copy2(path, config.DB_PATH)
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.row_factory = sqlite3.Row
    init_db()  # idempotent: re-applies migrations/defaults on whatever was just restored
    return True


def destroy_all_local_data():
    """Wipes every table back to a fresh-install state (owner re-seeded as
    the sole admin, default settings/texts restored). Does NOT by itself
    touch the actual messages sitting in the storage channel on Telegram —
    callers that also want those deleted should do it via the bot API
    before calling this, using the file rows this returns."""
    with _cursor() as cur:
        for table in ("users", "admins", "banned", "files", "force_sub_channels", "known_chats", "settings"):
            cur.execute(f"DELETE FROM {table}")
    init_db()
