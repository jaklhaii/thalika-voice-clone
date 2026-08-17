#!/usr/bin/env python3
"""
KM Voice Clone — Telegram Bot (single-file, stdlib only)
=========================================================
Professional button-based voice clone bot:
- Owner access control (whitelist, add/remove by Telegram ID)
- Per-user reference voice storage (each user's own list)
- High-quality generation via Colab GPU server (48kHz WAV)
- Reference required: text-only messages get NO voice output
- Inline keyboard step-by-step flow

Dependencies: Python 3.8+ stdlib ONLY (urllib, json, base64, os, sqlite3).
No pip install, no ffmpeg required.

Setup:
  BOT_TOKEN = "..."        # from @BotFather
  SERVER_URL = "..."       # https://xxxx.trycloudflare.com  (Colab output)
  OWNER_ID = 123456789     # your Telegram numeric ID

Run:  python3 bot.py
"""

import base64
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request

# ---------------- CONFIG ----------------
BOT_TOKEN = "8924460807:AAENhVbQfpSGa_vgVkvH5PP3fUEDrrJBd7c"
SERVER_URL = "https://karen-targets-hometown-knives.trycloudflare.com"  # Colab GPU server (changes each Colab session restart)
OWNER_ID = 8970380146

BOT_NAME = "KM Voice Clone"
BOT_VERSION = "1.0"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "km_voice.db")

# Maximum reference audio size to accept (MB) — Colab GPU, keep reasonable
MAX_REF_MB = 15

# ---------------- DB ----------------
_db = sqlite3.connect(DB_PATH, check_same_thread=False)
_db.executescript("""
CREATE TABLE IF NOT EXISTS allowed_users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    added_at INTEGER,
    added_by INTEGER
);
CREATE TABLE IF NOT EXISTS voices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    audio_b64 TEXT NOT NULL,      -- base64 wav data
    created_at INTEGER,
    UNIQUE(owner_id, name)
);
""")
_db.commit()


def user_allowed(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    if not OWNER_ID:
        return True  # no owner configured => open mode (dev only)
    row = _db.execute("SELECT 1 FROM allowed_users WHERE user_id = ?", (user_id,)).fetchone()
    return bool(row)


def add_allowed(user_id: int, username: str, by: int) -> None:
    _db.execute(
        "INSERT OR REPLACE INTO allowed_users (user_id, username, added_at, added_by) VALUES (?,?,?,?)",
        (user_id, username, int(time.time()), by),
    )
    _db.commit()


def remove_allowed(user_id: int) -> bool:
    _db.execute("DELETE FROM allowed_users WHERE user_id = ?", (user_id,))
    _db.commit()
    return bool(_db.total_changes)


def list_allowed():
    return _db.execute("SELECT user_id, username, added_at FROM allowed_users ORDER BY added_at").fetchall()


def save_voice(owner_id: int, name: str, audio_b64: str) -> bool:
    try:
        _db.execute(
            "INSERT OR REPLACE INTO voices (owner_id, name, audio_b64, created_at) VALUES (?,?,?,?)",
            (owner_id, name.strip().lower(), audio_b64, int(time.time())),
        )
        _db.commit()
        return True
    except Exception:
        return False


def get_voice(owner_id: int, name: str):
    row = _db.execute(
        "SELECT id, owner_id, name, audio_b64 FROM voices WHERE owner_id = ? AND name = ?",
        (owner_id, name.strip().lower()),
    ).fetchone()
    return row


def list_voices(owner_id: int):
    return _db.execute(
        "SELECT id, name, created_at FROM voices WHERE owner_id = ? ORDER BY created_at DESC",
        (owner_id,),
    ).fetchall()


def delete_voice(owner_id: int, name: str) -> bool:
    _db.execute("DELETE FROM voices WHERE owner_id = ? AND name = ?", (owner_id, name.strip().lower()))
    _db.commit()
    return True


# ---------------- TELEGRAM API ----------------

def api(method: str, payload: dict, timeout: int = 30):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"ok": False, "description": str(e)}


def api_file(method: str, files: dict, params: dict, timeout: int = 300):
    """Multipart/form-data POST for file uploads (sendVoice etc.)."""
    import http.client
    from io import BytesIO

    boundary = "----ManusBoundary7f8g9h0i"
    body = BytesIO()

    def write_field(name: str, value: str) -> None:
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(value.encode() + b"\r\n")

    def write_file(name: str, filename: str, content_type: str, data: bytes) -> None:
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode()
        )
        body.write(data)
        body.write(b"\r\n")

    for k, v in params.items():
        write_field(k, str(v))
    for k, (filename, content_type, data) in files.items():
        write_file(k, filename, content_type, data)
    body.write(f"--{boundary}--\r\n".encode())

    body_bytes = body.getvalue()
    conn = http.client.HTTPSConnection("api.telegram.org", timeout=timeout)
    try:
        conn.request(
            "POST", f"/bot{BOT_TOKEN}/{method}", body_bytes,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        resp = conn.getresponse()
        return json.loads(resp.read().decode())
    except Exception as e:
        return {"ok": False, "description": str(e)}
    finally:
        conn.close()


def send_message(chat_id, text: str, reply_markup=None, reply_to=None, parse="HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    return api("sendMessage", payload)


def kb_reply(rows):
    """Buttons BELOW the message (ReplyKeyboardMarkup) — one-touch, stays under every message."""
    keyboard = [[{"text": str(label)} for label in row] for row in rows]
    return {"keyboard": keyboard, "resize_keyboard": True}


def kb_reply_main():
    return kb_reply([
        ["Generate", "My Voices"],
        ["Settings", "Contact @Kmvclone"],
    ])


def kb_reply_voices():
    return kb_reply([["Add Voice", "List Voices"], ["Back to Menu"]])


def kb_reply_generate(voices):
    rows = [[v[1] for v in voices]] if voices else []
    rows.append(["Back to Menu"])
    return kb_reply(rows)


def kb_reply_admin():
    return kb_reply([["Add User", "Remove User"], ["List Users", "Server Info"], ["Back to Menu"]])


def kb_reply_remove(users):
    rows = [[str(uid) for uid, _u, _t in users]] if users else []
    rows.append(["Back"])
    return kb_reply(rows)


def kb_reply_select_voice(voices):
    rows = [[v[1] for v in voices]] if voices else []
    rows.append(["Cancel"])
    return kb_reply(rows)


def send_voice(chat_id, wav_bytes: bytes, caption: str = None, reply_to=None):
    files = {"voice": ("voice.wav", "audio/wav", wav_bytes)}
    params = {"chat_id": chat_id}
    if caption:
        params["caption"] = caption
    if reply_to is not None:
        params["reply_to_message_id"] = str(reply_to)
    return api_file("sendVoice", files, params)


# ---------------- VOICE GENERATION ----------------

def _progress_bar(pct: int, width: int = 10) -> str:
    filled = min(max(int(pct * width / 100), 0), width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def generate_voice(text: str, reference_b64: str, style: str = None, chat_id=None,
                   start_msg_id=None, timeout: int = 600):
    """Call the Colab GPU server /generate endpoint with progress updates."""
    payload = json.dumps({"text": text, "audio": reference_b64, "style": style}).encode()
    url = f"{SERVER_URL}/generate"
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    start = time.time()
    pct = 0
    last_pct = -1
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                time.sleep(1)
                now = time.time()
                # heuristic progress: estimate 150s total for a short text on T4;
                # scale toward 90% while waiting, jump to 100 at completion
                est = min(90, int((now - start) / 150.0 * 100)) if False else int(min(90, (now - start) / 6.0))
                est = max(est, pct)
                if est > pct and est - last_pct >= 10 and chat_id is not None:
                    last_pct = est
                    pct = est
                    api("editMessageText", {
                        "chat_id": chat_id,
                        "message_id": start_msg_id,
                        "text": f" Generating your cloned voice...\n[{_progress_bar(pct)}] {pct}%",
                        "parse_mode": "HTML",
                    })
                if resp.fp is not None:
                    if hasattr(resp.fp, "peek"):
                        try:
                            data = resp.fp.read()
                            result = json.loads(data.decode())
                            break
                        except Exception as e:
                            return None, f"Failed to read server response: {e}"
                    else:
                        data = resp.fp.read()
                        result = json.loads(data.decode())
                        break
    except urllib.error.HTTPError as e:
        return None, f"Server error {e.code}: {e.read().decode(errors='replace')[:200]}"
    except Exception as e:
        return None, f"Connection error: {e}"

    if not result.get("audio"):
        return None, result.get("error", "No audio returned from server")

    try:
        wav = base64.b64decode(result["audio"])
    except Exception:
        return None, "Failed to decode audio from server"

    # final progress update
    if chat_id is not None:
        api("editMessageText", {
            "chat_id": chat_id,
            "message_id": start_msg_id,
            "text": f" Generating your cloned voice...\n[{_progress_bar(100)}] 100%",
            "parse_mode": "HTML",
        })
    return wav, None


def server_health(timeout: int = 10):
    try:
        url = f"{SERVER_URL}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------- KEYBOARDS ----------------

def kb_main():
    return {
        "inline_keyboard": [
            [{"text": "  Generate  ", "callback_data": "menu:generate"}],
            [{"text": "  My Voices  ", "callback_data": "menu:voices"},
             {"text": "  Settings  ", "callback_data": "menu:settings"}],
            [{"text": " Contact Owner @Kmvclone ", "url": "https://t.me/Kmvclone"}],
        ]
    }


def kb_voices():
    return {"inline_keyboard": [[
        {"text": "  Add Voice  ", "callback_data": "voice:add"},
        {"text": "  List  ", "callback_data": "voice:list"},
    ]]}


def kb_voice_list(voices):
    rows = []
    for vid, name, _ in voices:
        rows.append([{"text": f" {name}", "callback_data": f"voice:use:{name}"}])
    rows.append([{"text": "  Back  ", "callback_data": "menu:voices"},
                 {"text": "  Main Menu  ", "callback_data": "menu:main"}])
    return {"inline_keyboard": rows}


def kb_generate():
    return {"inline_keyboard": [
        [{"text": "  Select Voice  ", "callback_data": "voice:list"},
         {"text": "  Paste Text  ", "callback_data": "gen:text"}],
        [{"text": "  Back  ", "callback_data": "menu:main"}],
    ]}


def kb_settings(is_owner: bool):
    rows = [[{"text": "  My Voices  ", "callback_data": "menu:voices"}]]
    if is_owner:
        rows.insert(0, [{"text": "  User Access  ", "callback_data": "admin:users"},
                        {"text": "  Server Info  ", "callback_data": "admin:server"}])
    rows.append([{"text": "  Back  ", "callback_data": "menu:main"}])
    return {"inline_keyboard": rows}


def kb_admin_users():
    return {"inline_keyboard": [
        [{"text": "  Add User  ", "callback_data": "admin:adduser"},
         {"text": "  Remove User  ", "callback_data": "admin:remuser"}],
        [{"text": "  List Users  ", "callback_data": "admin:listusers"},
         {"text": "  Back  ", "callback_data": "menu:settings"}],
    ]}


def kb_admin_remove(users):
    rows = [[{"text": f"  {uid}  ", "callback_data": f"admin:rm:{uid}"}] for uid, _u, _t in users]
    rows.append([{"text": "  Back  ", "callback_data": "admin:users"}])
    return {"inline_keyboard": rows if rows else [[{"text": "No users — Back", "callback_data": "admin:users"}]]}


# ---------------- HANDLERS ----------------

_state = {}  # chat_id -> {"step": ..., "data": ...}


def text_for(uid: int):
    is_owner = uid == OWNER_ID
    who = "Owner" if is_owner else "User"
    return (
        f"<b>{BOT_NAME}</b> v{BOT_VERSION}\n\n"
        f"Welcome, {who}!\n\n"
        f"<b>How it works</b>\n"
        f"1. Open <b>My Voices</b> → <b>Add Voice</b>\n"
        f"   then <b>send a voice/audio message</b>\n"
        f"2. The bot saves it as your reference\n"
        f"3. Open <b>Generate</b>, select your voice,\n"
        f"   then send the text you want spoken\n"
        f"4. You receive a cloned-voice WAV (48kHz)\n\n"
        f"<i>Only messages with a selected reference\n"
        f"voice are generated — text-only is ignored.</i>"
    )


def handle_message(update: dict):
    msg = update.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    uid = msg["from"]["id"]
    username = msg["from"].get("username", "")
    text = (msg.get("text") or "").strip()
    cmd, _, args = text.partition(" ")

    if not user_allowed(uid):
        return  # silently ignore non-allowed users

    st = _state.get(chat_id, {})

    # ---------- STATE MACHINE ----------
    if st.get("step") == "waiting_name":
        # any text input now = voice name
        if text:
            _state[chat_id] = {"step": "waiting_audio", "voice_name": text}
            send_message(chat_id, f" Now <b>send a voice message or audio file</b> to save as <b>{text}</b>:", reply_markup=None)
            return
        return

    if st.get("step") == "waiting_audio":
        # user must send a voice/audio file now
        audio = msg.get("voice") or msg.get("audio")
        if audio:
            # keep the highest-quality file available
            fid = (audio.get("file_id") or "").strip()
            if not fid:
                send_message(chat_id, "⚠️ Failed to read the audio file — please resend.", reply_markup=kb_reply_main())
                return
            send_message(chat_id, "⏳ Downloading your voice sample...")
            r = api("getFile", {"file_id": fid})
            fpath = (r.get("result") or {}).get("file_path", "")
            if not fpath:
                send_message(chat_id, "⚠️ Failed to download the audio — please resend.", reply_markup=kb_reply_main())
                return
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fpath}"
            try:
                with urllib.request.urlopen(url, timeout=120) as resp:
                    data = resp.read()
            except Exception:
                send_message(chat_id, "⚠️ Download failed — please resend.", reply_markup=kb_reply_main())
                return
            if len(data) > MAX_REF_MB * 1024 * 1024:
                send_message(chat_id, f"⚠️ File too large (max {MAX_REF_MB} MB). Send a shorter sample.", reply_markup=kb_reply_main())
                return
            name = st.get("voice_name", "default")
            if save_voice(uid, name, base64.b64encode(data).decode()):
                send_message(
                    chat_id,
                    f"✅ Voice <b>{name}</b> saved!\n\nYou can now use <b>Generate</b> → select this voice → send text.",
                    reply_markup=kb_reply_main(),
                )
            else:
                send_message(chat_id, "⚠️ Save failed — please try again.", reply_markup=kb_reply_main())
            _state[chat_id] = {}
            return
        else:
            send_message(
                chat_id,
                "⚠️ That is not a voice/audio file.\nPlease <b>send a voice message or audio file</b> now:",
                reply_markup=None,
            )
            return

    if st.get("step") == "waiting_text":
        if not text:
            send_message(chat_id, "⚠️ Please send the <b>text</b> you want spoken:", reply_markup=None)
            return
        voice = get_voice(uid, st.get("voice_name", ""))
        if not voice:
            send_message(chat_id, "⚠️ Reference voice missing — please add it again via <b>My Voices</b>.", reply_markup=kb_reply_main())
            _state[chat_id] = {}
            return
        start_r = send_message(chat_id, "  Generating your cloned voice... (1–3 min)\n[▓▓▓▓▓▓▓▓▓▓] 0%")
        start_msg_id = (start_r.get("result") or {}).get("message_id")
        wav, err = generate_voice(text, voice[3], chat_id=chat_id, start_msg_id=start_msg_id)
        if err:
            send_message(chat_id, f"⚠️ Generation failed:\n{err}", reply_markup=kb_reply_main())
            _state[chat_id] = {}
            return
        send_voice(chat_id, wav, caption=f"{BOT_NAME} — voice: {voice[2]}", reply_markup=kb_reply_main())
        _state[chat_id] = {}
        return

    if st.get("step") == "waiting_adduser":
        # expects: user ID (numeric) or reply to the target user
        target = None
        replied = msg.get("reply_to_message")
        if replied:
            target = replied["from"]["id"]
        elif text.isdigit():
            target = int(text)
        if not target:
            send_message(chat_id, "⚠️ Send the user's <b>numeric Telegram ID</b>, or reply to their message:", reply_markup=None)
            return
        if user_allowed(target):
            send_message(chat_id, "ℹ️ That user already has access.", reply_markup=kb_reply_admin())
            _state[chat_id] = {}
            return
        add_allowed(target, "", uid)
        send_message(chat_id, f"✅ User <code>{target}</code> added to allowed list.", reply_markup=kb_reply_admin())
        _state[chat_id] = {}
        return

    if st.get("step") == "waiting_remuser":
        target = None
        replied = msg.get("reply_to_message")
        if replied:
            target = replied["from"]["id"]
        elif text.isdigit():
            target = int(text)
        if not target:
            send_message(chat_id, "⚠️ Send the <b>numeric Telegram ID</b>, or reply to their message:", reply_markup=None)
            return
        remove_allowed(target)
        send_message(chat_id, f"✅ User <code>{target}</code> removed.", reply_markup=kb_reply_admin())
        _state[chat_id] = {}
        return

    # ---------- COMMANDS ----------
    # ---------- REPLY BUTTON HANDLERS (message text matches a button label) ----------
    if text == "Generate":
        voices = list_voices(uid)
        note = f"You have {len(voices)} saved voice(s)." if voices else "You have <b>no voices yet</b> — add one first."
        send_message(chat_id, f"<b>Generate</b>\n{note}\n\nTap your voice below, then send the text:",
                     reply_markup=kb_reply_generate(voices))
        if voices:
            _state[chat_id] = {"step": "waiting_voice_select"}
        else:
            _state[chat_id] = {}
        return
    if text == "My Voices":
        voices = list_voices(uid)
        note = f"You have <b>{len(voices)}</b> saved voice(s)." if voices else "No voices saved yet."
        send_message(chat_id, f"<b>My Voices</b>\n{note}", reply_markup=kb_reply_voices())
        return
    if text == "Settings":
        if uid == OWNER_ID:
            send_message(chat_id, "<b>Settings (Owner)</b>\nOwner controls:", reply_markup=kb_reply_admin())
        else:
            send_message(chat_id, "<b>Settings</b>", reply_markup=kb_reply_main())
        return
    if text == "Contact @Kmvclone":
        send_message(chat_id, "Contact the owner: <b>@Kmvclone</b>\nhttps://t.me/Kmvclone", reply_markup=kb_reply_main())
        return
    if text == "Add Voice":
        send_message(chat_id, " What <b>name</b> for this voice? (one word, e.g. myvoice):", reply_markup=None)
        _state[chat_id] = {"step": "waiting_name"}
        return
    if text == "List Voices":
        voices = list_voices(uid)
        if not voices:
            send_message(chat_id, " No voices saved yet.\n<b>Add Voice</b> → send a voice message.", reply_markup=kb_reply_voices())
            return
        _state[chat_id] = {"step": "waiting_voice_select"}
        send_message(chat_id, "<b>Select a voice to use:</b>", reply_markup=kb_reply_select_voice(voices))
        return
    if text == "Add User":
        if uid != OWNER_ID:
            send_message(chat_id, "Owner only.", reply_markup=kb_reply_main())
            return
        send_message(chat_id, " Send the user's <b>numeric Telegram ID</b>, or reply-to their message:")
        _state[chat_id] = {"step": "waiting_adduser"}
        return
    if text == "Remove User":
        if uid != OWNER_ID:
            send_message(chat_id, "Owner only.", reply_markup=kb_reply_main())
            return
        users = list_allowed()
        _state[chat_id] = {"step": "waiting_remuser"}
        send_message(chat_id, "<b>Select a user ID below</b> to remove\n(or send/reply with their ID):",
                     reply_markup=kb_reply_remove(users))
        return
    if text == "List Users":
        if uid != OWNER_ID:
            send_message(chat_id, "Owner only.", reply_markup=kb_reply_main())
            return
        users = list_allowed()
        if not users:
            txt = " No allowed users besides owner."
        else:
            txt = "\n".join(f" • <code>{u}</code> (@{n or '?'})" for u, n, _ in users)
        send_message(chat_id, f"<b>Allowed users:</b>\n{txt}", reply_markup=kb_reply_admin())
        return
    if text == "Server Info":
        if uid != OWNER_ID:
            send_message(chat_id, "Owner only.", reply_markup=kb_reply_main())
            return
        ok = server_health()
        send_message(
            chat_id,
            f"<b>Server status:</b> {'🟢 Online' if ok else '🔴 Offline'}\n"
            f"URL: <code>{SERVER_URL}</code>",
            reply_markup=kb_reply_admin(),
        )
        return
    if text == "Back to Menu":
        _state[chat_id] = {}
        send_message(chat_id, text_for(uid), reply_markup=kb_reply_main())
        return
    if text == "Cancel":
        _state[chat_id] = {}
        send_message(chat_id, "Cancelled.", reply_markup=kb_reply_main())
        return

    # voice selection from the Generate / List Voices menus
    if st.get("step") == "waiting_voice_select":
        voices = list_voices(uid)
        names = [v[1] for v in voices]
        if text in names:
            v = get_voice(uid, text)
            if not v:
                send_message(chat_id, "⚠️ Voice not found — please add it again.", reply_markup=kb_reply_voices())
                _state[chat_id] = {}
                return
            _state[chat_id] = {"step": "waiting_text", "voice_name": text}
            send_message(chat_id, f"✅ Voice <b>{text}</b> selected.\n\nNow <b>send the text</b> you want spoken:",
                         reply_markup=kb_reply([["Cancel"]]))
            return
        return

    if st.get("step") == "waiting_remuser" and uid == OWNER_ID:
        # button label is the user's numeric id, or typed id
        if text.isdigit():
            target = int(text)
            remove_allowed(target)
            send_message(chat_id, f"✅ User <code>{target}</code> removed.", reply_markup=kb_reply_admin())
            _state[chat_id] = {}
            return
        return

    # ---------- COMMANDS ----------
    if cmd in ("/start", "/help"):
        send_message(chat_id, text_for(uid), reply_markup=kb_reply_main())
        return

    if cmd == "/voice" and args.strip():
        # quick mode: /voice <text> with currently-selected voice (shortcut)
        voices = list_voices(uid)
        if not voices:
            send_message(chat_id, "⚠️ No voices saved yet.\n<b>My Voices</b> → <b>Add Voice</b> first.", reply_markup=kb_reply_main())
            return
        voice = get_voice(uid, voices[0][1])
        if not voice:
            send_message(chat_id, "⚠️ Reference voice missing.", reply_markup=kb_reply_main())
            return
        start_r = send_message(chat_id, "  Generating...\n[▓▓▓▓▓▓▓▓▓▓] 0%")
        start_msg_id = (start_r.get("result") or {}).get("message_id")
        wav, err = generate_voice(args.strip(), voice[3], chat_id=chat_id, start_msg_id=start_msg_id)
        if err:
            send_message(chat_id, f"⚠️ Failed:\n{err}", reply_markup=kb_reply_main())
            return
        send_voice(chat_id, wav, caption=f"{BOT_NAME} — voice: {voice[2]}", reply_markup=kb_reply_main())
        return

    if cmd in ("/voice",) and not args.strip():
        send_message(chat_id, "Send <b>/voice your text here</b> after selecting a voice in <b>My Voices</b>.", reply_markup=kb_reply_main())
        return

    # ---------- BACKWARD-COMPAT INLINE BUTTONS ----------
    if cmd == "/menu" or cmd == "/back":
        send_message(chat_id, text_for(uid), reply_markup=kb_reply_main())
        return

    # Plain text (not a command) — bot does NOT generate without reference.
    # Friendly pointer instead.
    if text and not cmd.startswith("/"):
        send_message(
            chat_id,
            "ℹ️ Text-only messages are not generated.\n"
            "Use the menu: <b>My Voices</b> → add a voice → then <b>Generate</b>.",
            reply_markup=kb_reply_main(),
        )
        return


def handle_callback(update: dict):
    cb = update.get("callback_query")
    if not cb:
        return
    chat_id = cb["message"]["chat"]["id"]
    uid = cb["from"]["id"]
    mid = cb["message"]["message_id"]
    if not user_allowed(uid):
        api("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "Access denied."})
        return
    data = cb.get("data", "")
    _state[chat_id] = {}

    # --- main menu ---
    if data == "menu:main":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        send_message(chat_id, text_for(uid), reply_markup=kb_reply_main())
        return
    if data == "menu:generate":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        voices = list_voices(uid)
        note = f"You have {len(voices)} saved voice(s)." if voices else "You have <b>no voices yet</b> — add one first."
        send_message(chat_id, f"<b>Generate</b>\n{note}\n\nSelect a voice, then send the text:", reply_markup=kb_reply_generate(voices))
        return
    if data == "menu:voices":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        voices = list_voices(uid)
        note = f"You have <b>{len(voices)}</b> saved voice(s)." if voices else "No voices saved yet."
        send_message(chat_id, f"<b>My Voices</b>\n{note}", reply_markup=kb_reply_voices())
        return
    if data == "menu:settings":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        send_message(chat_id, "<b>Settings</b>", reply_markup=kb_settings(uid == OWNER_ID))
        return

    # --- voices ---
    if data == "voice:add":
        api("answerCallbackQuery", {"callback_query_id": cb["id"], "show_alert": False})
        api("sendMessage", {"chat_id": chat_id, "text": " What name for this voice? (one word, e.g. default)"})
        _state[chat_id] = {"step": "waiting_name"}
        return
    if data == "voice:list":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        voices = list_voices(uid)
        if not voices:
            send_message(chat_id, " No voices saved yet.\n<b>Add Voice</b> → send a voice message.", reply_markup=kb_reply_voices())
            return
        send_message(chat_id, "<b>Select a voice to use:</b>", reply_markup=kb_reply_select_voice(voices))
        return
    if data.startswith("voice:use:"):
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        name = data[len("voice:use:"):]
        v = get_voice(uid, name)
        if not v:
            send_message(chat_id, "⚠️ Voice not found — please add it again.", reply_markup=kb_reply_voices())
            return
        _state[chat_id] = {"step": "waiting_text", "voice_name": name}
        send_message(chat_id, f"✅ Voice <b>{name}</b> selected.\n\nNow <b>send the text</b> you want spoken:")
        return
    if data == "gen:text":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        voices = list_voices(uid)
        if not voices:
            send_message(chat_id, "⚠️ No voices saved yet — <b>Add Voice</b> first.", reply_markup=kb_reply_voices())
            return
        # default to first (most recent)
        _state[chat_id] = {"step": "waiting_text", "voice_name": voices[0][1]}
        send_message(chat_id, f"✅ Using voice <b>{voices[0][1]}</b>.\n\nNow <b>send the text</b> you want spoken:")
        return

    # --- admin ---
    if data == "admin:users":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        send_message(chat_id, "<b>User Access Management</b>", reply_markup=kb_reply_admin())
        return
    if data == "admin:adduser":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        send_message(chat_id, " Send the user's <b>numeric Telegram ID</b>, or reply-to their message:")
        _state[chat_id] = {"step": "waiting_adduser"}
        return
    if data == "admin:remuser":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        users = list_allowed()
        send_message(chat_id, "<b>Select user to remove:</b>\n(or send/reply with their ID)", reply_markup=kb_reply_remove(users))
        _state[chat_id] = {"step": "waiting_remuser"}
        return
    if data == "admin:listusers":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        users = list_allowed()
        if not users:
            txt = " No allowed users besides owner."
        else:
            txt = "\n".join(f" • <code>{u}</code> (@{n or '?'})" for u, n, _ in users)
        send_message(chat_id, f"<b>Allowed users:</b>\n{txt}", reply_markup=kb_reply_admin())
        return
    if data.startswith("admin:rm:"):
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        target = int(data[len("admin:rm:"):])
        remove_allowed(target)
        send_message(chat_id, f"✅ User <code>{target}</code> removed.", reply_markup=kb_reply_admin())
        return
    if data == "admin:server":
        api("answerCallbackQuery", {"callback_query_id": cb["id"]})
        ok = server_health()
        send_message(
            chat_id,
            f"<b>Server status:</b> {'🟢 Online' if ok else '🔴 Offline'}\n"
            f"URL: <code>{SERVER_URL}</code>",
            reply_markup=kb_reply_admin(),
        )
        return

    api("answerCallbackQuery", {"callback_query_id": cb["id"]})


# ---------------- POLL LOOP ----------------

def poll(offset: int, timeout: int = 30):
    return api("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]}, timeout=timeout + 10)


def run():
    if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_"):
        print("ERROR: set BOT_TOKEN, SERVER_URL, OWNER_ID at the top of this file")
        raise SystemExit(1)
    print(f"[{BOT_NAME}] starting... (owner={OWNER_ID})")
    print(f"[{BOT_NAME}] server: {SERVER_URL}")
    if not server_health(timeout=15):
        print(f"[{BOT_NAME}] WARNING: server health check failed — check SERVER_URL")

    offset = 0
    while True:
        try:
            r = poll(offset)
        except Exception as e:
            print(f"[{BOT_NAME}] poll error: {e}; retrying in 5s")
            time.sleep(5)
            continue
        if not r.get("ok"):
            print(f"[{BOT_NAME}] api error: {r.get('description')}; retrying in 5s")
            time.sleep(5)
            continue
        for upd in r.get("result", []):
            offset = max(offset, upd.get("update_id", 0) + 1)
            try:
                handle_message(upd)
                handle_callback(upd)
            except Exception as e:
                print(f"[{BOT_NAME}] handler error: {e}")
        time.sleep(0.2)


if __name__ == "__main__":
    run()
