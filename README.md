# 🗂 Telegram File Store Bot

A secure, advanced file-store & delivery bot with:

- 📥 **Receive-only for regular users** — they can only download via shared links; uploading is admin/owner-only
- ✅ **Force-subscribe re-check** — every `/start` (with or without a link) is gated; the prompt only ever shows channels the user *hasn't* joined yet, narrowing down as they join, and it's re-checked fresh every single time (never cached)
- ⌨️ **Bottom reply-keyboard navigation** for admins (Root → Admin Panel → Settings/Users/Admins/Files/Backup, Force-Sub nested under Settings) alongside inline keyboards for dynamic pick-lists, toggles, and confirmations — every submenu has a Back button
- 🔎 **Live admin-channel detection** — passive tracking via Telegram's membership events, *plus* active verify-on-demand (the moment you forward a message or type an ID, it's checked live and cached) and a 🔄 Refresh button that re-verifies everything already known
- 📤 Store any file kind (document/video/photo/audio/voice/GIF/sticker) with its caption, get a shareable deep link
- 🔗 Deep links show **only** a status message → the file → a timer message — nothing else
- 🔐 **Multiple** force-subscribe channels/groups — pick from bot-admin channels, tap to add/remove
- 🛡 **Multiple** admins, with a protected, un-removable owner — add/remove by tapping a name, no typing IDs
- ⏱ 5-minute auto-delete timer by default (configurable), live countdown bar, and a "don't forward" warning that **only shows when Content Protection is OFF** (when it's ON, Telegram itself already blocks forwarding, so the warning is skipped)
- 🚫 Ban / unban users by tapping a name, 📢 broadcast to all users, 📥 export the user list (name + status) to a `.txt`
- 🗄 Files Management — browse stored files **by filename**, get a link, remove a file (also deletes it from the storage channel), or reissue its link ID
- 💾 **Backup / Restore / Destroy** — Backup Data snapshots all metadata + config (never the file bytes — those stay on Telegram) as a downloadable `.db`; Restore Data loads a backup back in, picking up exactly where it left off, even on a brand-new host; Destroy Data wipes everything (including deleting the actual messages from the storage channel) back to a fresh install
- 🎛 **Edit Mode** — welcome message, help/about text, warnings, and prompts are all editable live from Settings, not hardcoded
- 🌐 **DevUploads.com mirroring** — every upload is automatically mirrored to DevUploads too (both links saved and shown); manage your DevUploads account, files, and folders — rename, delete, remote-upload — directly from the bot. API key lives in `.env` or is set/changed live from the bot itself
- 🎯 **Exactly one live menu at a time** — opening a new picker/action screen always retires whichever one was open before, so a stale "Remove File" screen from two menus ago can never accidentally delete something you're not even looking at anymore
- ⬅️ **True one-step Back** — Back always closes whatever's immediately open (a picker, a prompt) and lands on its own hub first, never skipping past it to a level above
- 💾 SQLite database (reliable, atomic, single-file, easy to back up)
- 🔁 Two-layer auto-restart (in-process backoff loop + systemd `Restart=always`)
- 🔒 No secrets in code — everything sensitive lives in `.env`

> **Note on auto-detected channels:** Telegram's Bot API has no "list every chat I'm in" endpoint. The bot learns which channels/groups it administers two ways: passively, the moment it's promoted/demoted anywhere while running; and actively, the instant you point it at a chat by forwarding a message or typing an ID — that chat gets verified live and remembered from then on. If a channel doesn't show up in a picker yet, forward one message from it (or use 🔄 Refresh Detected Channels) and it'll appear immediately.

> **Note on DevUploads:** DevUploads runs on the XFileSharingPro (XFS) script family. `account/info`, `account/stats`, `upload/server`, and `file/list` were verified directly against devuploads.com; every other endpoint follows that same well-established convention. Two endpoints (deleting a file or folder) aren't in the base XFS reference docs — they're extremely common additions on sites like this one, but if either ever errors for you, that's the one pair to double-check against your account's own API panel. Everything lives in one file (`devuploads.py`), one method per endpoint, so fixing one thing never touches anything else.

---

## 1. What you'll need before you start

- A VPS (any Ubuntu/Debian server works — even the cheapest 1 vCPU / 512MB–1GB plan is enough)
- A Telegram account
- 10–15 minutes

---

## 2. Create your bot on Telegram

1. Open Telegram, search for **@BotFather**, and start a chat.
2. Send `/newbot` and follow the prompts (choose a name and a username ending in `bot`).
3. BotFather gives you a **token** like `123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — copy it, you'll need it for `.env`.
4. Optional but recommended: send `/setprivacy` → select your bot → **Disable**, so it can see files sent to it in groups if you ever add it to one.

## 3. Get your own Telegram user ID (this makes you the owner/super-admin)

1. Search for **@userinfobot** on Telegram and start it.
2. It replies with your numeric **user ID**. Copy it — this becomes `OWNER_ID`.

## 4. Create a private storage channel

This is where uploaded files are actually kept (the bot copies files from here to users).

1. Create a new **private** Telegram channel (e.g. "My File Vault").
2. Add your bot to it as an **administrator** (needs "Post Messages" at minimum).
3. Send any message in the channel, then forward that message to **@userinfobot** (or use any "get chat ID" bot) to learn the channel's numeric ID — it looks like `-1001234567890`.
   - Easiest alternative: you'll set this live from inside the bot's admin panel (Step 9) by simply **forwarding a message from the channel** to the bot — it detects the ID automatically, no manual copying needed.

## 5. (Optional) Create one or more force-subscribe channels

If you want users to join a channel before they can download files:

1. Create a **public** channel (so you have an invite link like `https://t.me/yourchannel`), or a private one with an invite link.
2. Add your bot as an **admin** in it (needs "Ban/Add Users" permission to check membership).
3. You'll register it from the admin panel in Step 9 — you can add as many of these as you like.

---

## 6. Deploy to your VPS

SSH into your VPS as **root** (this whole guide assumes a root shell — no `sudo` is used anywhere; most fresh VPS instances give you root by default, otherwise switch to it first with `su -`):

```bash
# 1. Install git if you don't have it
apt update && apt install -y git

# 2. Clone your copy of this repository
git clone https://github.com/itisak-51/TG-Files-Bot.git
cd TG-Files-Bot

# 3. Run the installer (creates a virtualenv, installs dependencies, makes .env)
chmod +x install.sh
./install.sh

# 4. Fill in your secrets
nano .env
```

In `.env`, set:
```
BOT_TOKEN=your_botfather_token
OWNER_ID=your_numeric_user_id
```
Save with `Ctrl+O`, `Enter`, then exit with `Ctrl+X`.

## 7. Test it manually first

```bash
source venv/bin/activate
python3 bot.py
```

Open Telegram, message your bot with `/start`. You should see the welcome menu — and a `/` command picker with `start`, `help`, and `cancel` already registered (admins additionally get `admin`, `setstorage`, and `checkstorage` in their own menu — see "Command menus" below). Press `Ctrl+C` to stop the test run once it works.

## 8. Run it 24/7 (pick ONE of the two options below)

### Option A — PM2 (recommended if you're used to Node.js process management)

[PM2](https://pm2.keymetrics.dev/) isn't Node-only — it can supervise any executable, including this Python bot, and gives you the same `pm2 list` / `pm2 logs` / `pm2 restart` workflow you'd use for a Node app.

```bash
# 1. Install Node.js + PM2 (skip if you already have them) — run as root, no sudo
curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
apt install -y nodejs
npm install -g pm2

# 2. Make sure the venv + dependencies exist (install.sh already did this)
mkdir -p logs

# 3. Start the bot under PM2 using the included ecosystem.config.js
pm2 start ecosystem.config.js

# 4. Make PM2 itself survive a reboot
pm2 save
pm2 startup            # run the command it prints (you're already root, so no sudo needed)
```

Everyday PM2 commands:
```bash
pm2 list                    # see status, uptime, restart count
pm2 logs filestore-bot      # live logs
pm2 restart filestore-bot   # restart after a code update
pm2 stop filestore-bot      # stop it
```
To update the code later: `git pull`, then `pm2 restart filestore-bot`.

### Option B — systemd (built into every Linux distro, no extra install)

```bash
# Edit the service file to confirm the paths match where you cloned the repo
nano filestore-bot.service
# Update WorkingDirectory and ExecStart to your actual clone path
# (the default User=root matches the no-sudo, root-shell workflow this guide uses —
# change it only if you deliberately want to run the bot as a different user).

# Install the service (already root, so no sudo)
cp filestore-bot.service /etc/systemd/system/filestore-bot.service
systemctl daemon-reload
systemctl enable filestore-bot     # start automatically on server reboot
systemctl start filestore-bot      # start it now

# Check it's running
systemctl status filestore-bot

# View live logs
journalctl -u filestore-bot -f
```

To update the code later: `git pull`, then `systemctl restart filestore-bot`.

Both options restart the bot within seconds of a crash and bring it back after a server reboot — use whichever tooling you're more comfortable managing. Don't run both at once (they'd fight over the same bot token).

---

## 9. First-time setup inside the bot (all live, no restarts needed)

1. Message your bot `/admin` (you're the owner, so this works immediately).
2. Set your storage channel the reliable way — as a direct command that actively checks the bot's access, instead of the button flow (which needs a "pending" state that's easy to lose):
   ```
   /setstorage -1001234567890
   ```
   If it fails, the bot tells you exactly why (wrong ID format, bot not in the channel, or bot in the channel but not an admin). You can re-check anytime with `/checkstorage`.

   The button flow (**Settings → Storage Channel**) also works — you can either send the numeric ID or forward a message from the channel — but `/setstorage` is the more foolproof option since it can't lose track of what you're doing.
3. *(Optional)* **Force-Sub Channels → Add Force-Sub Channel** → send:
   ```
   -1001234567890 | My Channel | https://t.me/mychannel
   ```
   Repeat for as many channels as you want. Users must join **all** of them.
4. *(Optional)* **Settings → Welcome Message** to customize the greeting (`{name}` is replaced with the user's first name).
5. *(Optional)* **Settings → Auto-Delete Timer** to change how long delivered files stay before auto-deleting (default 60s; send `0` to disable).
6. *(Optional)* **Admins → Add Admin** to give trusted people admin access — send their numeric user ID (get it from @userinfobot, same as Step 3).

That's it — send the bot a file and it will hand you a shareable link immediately.

---

## Command menus

The bot registers its slash commands with Telegram itself (via `set_my_commands`), so they show up in the native `/` picker in the chat, not just as things the bot happens to respond to:

- **Everyone** sees: `/start`, `/help`, `/cancel`
- **Admins** additionally see: `/admin`, `/setstorage`, `/checkstorage` — but only in their own chat with the bot (other users never see admin commands in their picker)

This updates automatically: the moment someone is added as an admin (via **Admins → Add Admin** or by matching `OWNER_ID`), their command menu is refreshed; removing an admin drops them back to the public list. No restart needed.

## Commands

| Command | Description |
|---|---|
| `/start` | Open the main menu (or redeem a file link: `/start <file_id>`) |
| `/help` | Show usage instructions |
| `/admin` | Open the admin panel (admins only) |
| `/cancel` | Cancel whatever text input the bot is currently waiting for |
| `/setstorage <channel_id>` | Directly set the storage channel, with a live permission check (admins only) |
| `/checkstorage` | Diagnose why the configured storage channel isn't working (admins only) |

## Admin Panel Map

```
🛠 Admin Panel
├── 📊 Statistics         — live counts of users, files, admins, etc.
├── ⚙️ Settings
│   ├── 🔒 Storage Channel
│   ├── ✍️ Welcome Message
│   ├── ⏱ Auto-Delete Timer
│   └── 🛡 Toggle Protect Content   (disables forwarding/saving of delivered files)
├── 👥 Users
│   ├── 🚫 Ban User / ✅ Unban User
│   └── 📥 Export User IDs
├── 🛡 Admins              — add/remove admins (owner is permanent)
├── 🔐 Force-Sub Channels  — add/remove any number of required channels
├── 📢 Broadcast           — message every tracked user at once
└── 🗑 Manage Files
    ├── 🗑 Delete File by ID
    ├── 📄 List Recent Files
    └── 💣 Clear ALL Files
```

---

## Project structure

```
telegram-filestore-bot/
├── bot.py                 # entry point + auto-restart loop
├── config.py               # loads & validates .env
├── database.py              # SQLite data layer
├── keyboards.py             # all inline keyboard layouts
├── handlers/
│   ├── start.py             # /start, /help, /cancel, /admin
│   ├── admin_commands.py    # /setstorage, /checkstorage (state-independent fallbacks)
│   ├── callbacks.py         # every inline-button action
│   ├── text_input.py        # admin "send me a value" flows
│   ├── upload.py             # incoming file → storage channel
│   └── delivery.py           # force-sub check + file delivery + countdown
├── requirements.txt
├── .env.example
├── filestore-bot.service    # systemd unit for 24/7 uptime (Option B)
├── ecosystem.config.js      # PM2 process definition for 24/7 uptime (Option A)
├── install.sh                # one-shot VPS installer
└── .gitignore
```

## Backing up your data

Everything (users, admins, files, settings) lives in one file: `filestore.db`. To back it up:

```bash
cp filestore.db filestore.db.backup
```

## Troubleshooting

- **Bot doesn't respond at all** → check `journalctl -u filestore-bot -f` for errors; confirm `BOT_TOKEN` in `.env` is correct.
- **"Storage channel is not configured yet" / storage channel won't save** → run `/setstorage -1001234567890`, then `/checkstorage` to see exactly what's wrong. Common causes: the ID is missing its `-100` prefix, the bot was never added to the channel, or it's a member but not an admin there.
- **Force-sub check always fails** → make sure the bot is an **admin** in that channel (not just a member).
- **File upload fails with a permission error** → the bot needs "Post Messages" permission in the storage channel.
- **Owner locked out** → `OWNER_ID` in `.env` is always treated as admin regardless of the database, so double-check it matches your real Telegram user ID from @userinfobot.

## Security notes

- Never commit your real `.env` file — it's already excluded via `.gitignore`.
- If your bot token ever leaks, revoke it instantly via @BotFather → `/revoke`.
- Keep your storage channel **private** — it's the bot's raw file vault.
