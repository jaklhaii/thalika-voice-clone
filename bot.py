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
SERVER_URL = "https://sally-dis-tune-indicated.trycloudflare.com"  # Colab GPU server (changes each Colab session restart)
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
    return {"keyboard": keyboard, "resize_keyboard": True, "is_persistent": False}


def kb_reply_main():
    return kb_reply([
        ["🔊 အသံထုတ်မည်", "🎤 ကျွန်တော့်အသံများ"],
        ["⚙️ ဆောင်ရွက်ချက်များ", "ဆက်သွယ်ရန် @Kmvclone"],
    ])


def kb_reply_voices():
    return kb_reply([["➕ အသံထည့်မည်", "📋 အသံစာရင်းကြည့်မည်"], ["◀️ မူလစာမျက်နှာ"]])


def kb_reply_generate(voices):
    rows = [[f"🎙 {v[1]}" for v in voices]] if voices else []
    rows.append(["◀️ မူလစာမျက်နှာ"])
    return kb_reply(rows)


def kb_reply_admin():
    return kb_reply([["➕ အသုံးပြုသူထည့်မည်", "➖ အသုံးပြုသူဖယ်မည်"], ["📋 အသုံးပြုသူစာရင်း", "🖥 Server အခြေအနေ"], ["◀️ မူလစာမျက်နှာ"]])


def kb_reply_remove(users):
    rows = [[str(uid) for uid, _u, _t in users]] if users else []
    rows.append(["◀️ နောက်ကျပြန်"])
    return kb_reply(rows)


def kb_reply_select_voice(voices):
    rows = [[v[1] for v in voices]] if voices else []
    rows.append(["❌ ပယ်ဖြက်မည်"])
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


# ---------------- KEYBOARDS (ReplyKeyboardMarkup — buttons below message) ----------------




# ---------------- HANDLERS ----------------

_state = {}  # chat_id -> {"step": ..., "data": ...}


def text_for(uid: int):
    is_owner = uid == OWNER_ID
    who = "ပိုင်ရှင်" if is_owner else "အသုံးပြုသူ"
    return (
        f"<b>{BOT_NAME}</b> v{BOT_VERSION}\n\n"
        f"ကြိုဆိုပါတယ် {who}!\n\n"
        f"<b>အသုံးပြုပုံ</b>\n"
        f"1. <b>ကျွန်တော့်အသံများ</b> → <b>အသံထည့်မည်</b> ကို နှိပ်ပြီး\n"
        f"   <b>အသံ message (သို့) audio ဖိုင်</b> ပို့ပါ\n"
        f"2. Bot က အသံကို သင့် reference အဖြစ် သိမ်းပေးပါမယ်\n"
        f"3. <b>အသံထုတ်မည်</b> → သင့်အသံကို ရွေးပြီး\n"
        f"   ပြောစေချင်တဲ့ <b>စာသား</b> ပို့ပါ\n"
        f"4. Clone လုပ်ထားတဲ့ အသံ WAV (48kHz) ပြန်ရပါမယ်\n\n"
        f"<i>ရွေးထားတဲ့ reference အသံမရှိဘဲ စာသားသီးသန့်ပို့ရင်\n"
        f"အသံမထုတ်ပေးပါ — ပစ်ချင်ပါမယ်။</i>"
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
            send_message(chat_id, f"⏳ ယခု <b>{text}</b> အဖြစ်သိမ်းမယ့ <b>အသံ message (သို့) audio ဖိုင်</b> ပို့ပေးပါ:", reply_markup=None)
            return
        return

    if st.get("step") == "waiting_audio":
        # user must send a voice/audio file now
        audio = msg.get("voice") or msg.get("audio")
        if audio:
            # keep the highest-quality file available
            fid = (audio.get("file_id") or "").strip()
            if not fid:
                send_message(chat_id, "⚠️ ဖိုင်ဖတ်မရဘူး — ပြန်ပို့ပေးပါ။", reply_markup=kb_reply_main())
                return
            send_message(chat_id, "⏳ အသံနမူနာ ယူနေပါတယ်...")
            r = api("getFile", {"file_id": fid})
            fpath = (r.get("result") or {}).get("file_path", "")
            if not fpath:
                send_message(chat_id, "⚠️ အသံ download မရဘူး — ပြန်ပို့ပေးပါ။", reply_markup=kb_reply_main())
                return
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fpath}"
            try:
                with urllib.request.urlopen(url, timeout=120) as resp:
                    data = resp.read()
            except Exception:
                send_message(chat_id, "⚠️ Download မအောင်မြင် — ပြန်ပို့ပေးပါ။", reply_markup=kb_reply_main())
                return
            if len(data) > MAX_REF_MB * 1024 * 1024:
                send_message(chat_id, f"⚠️ ဖိုင်ကြီးလွန်းပါတယ် (အမြင်းဆုံး {MAX_REF_MB} MB)။ ပိုတိုတဲ့ အသံနမူနာ ပို့ပေးပါ။", reply_markup=kb_reply_main())
                return
            name = st.get("voice_name", "default")
            if save_voice(uid, name, base64.b64encode(data).decode()):
                send_message(
                    chat_id,
                    f"✅ အသံ <b>{name}</b> သိမ်းဆီးပြီးပါပြီ!\n\nယခု <b>🔊 အသံထုတ်မည်</b> → ဒီအသံကို ရွေး → စာသားပို့ပါ။",
                    reply_markup=kb_reply_main(),
                )
            else:
                send_message(chat_id, "⚠️ သိမ်းလို့မရဘူး — ထပ်ကြိုးစားကြည့်ပါ။", reply_markup=kb_reply_main())
            _state[chat_id] = {}
            return
        else:
            send_message(
                chat_id,
                "⚠️ ဒါက အသံ (သို့) audio ဖိုင် မဟုတ်ပါ။\nယခု <b>အသံ message (သို့) audio ဖိုင်</b> ပို့ပေးပါ:",
                reply_markup=None,
            )
            return

    if st.get("step") == "waiting_text":
        if not text:
            send_message(chat_id, "⚠️ အသံထုတ်ချင်တဲ့ <b>စာသား</b> ကို ပို့ပေးပါ:", reply_markup=None)
            return
        voice = get_voice(uid, st.get("voice_name", ""))
        if not voice:
            send_message(chat_id, "⚠️ Reference အသံမရှိတော့ပါ — <b>🎤 ကျွန်တော့အသံများ</b> ကနေ ထပ်ထည့်ပေးပါ။", reply_markup=kb_reply_main())
            _state[chat_id] = {}
            return
        start_r = send_message(chat_id, "🎙 Clone အသံ ထုတ်နေပါတယ်... (1–3 မိနစ်)\n[▓▓▓▓▓▓▓▓▓▓] 0%")
        start_msg_id = (start_r.get("result") or {}).get("message_id")
        wav, err = generate_voice(text, voice[3], chat_id=chat_id, start_msg_id=start_msg_id)
        if err:
            send_message(chat_id, f"⚠️ အသံထုတ်မှု မအောင်မြင်:\n{err}", reply_markup=kb_reply_main())
            _state[chat_id] = {}
            return
        send_voice(chat_id, wav, caption=f"{BOT_NAME} — အသံ: {voice[2]}", reply_markup=kb_reply_main())
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
            send_message(chat_id, "⚠️ <b>Telegram ID (ဂဏန်း)</b> ပို့ပါ (သို့) သူ့ message ကို reply ပြီး ပို့ပါ:", reply_markup=None)
            return
        if user_allowed(target):
            send_message(chat_id, "ℹ️ ဒီသူ့မှာ အခွင့်အရေး ရှိပြီးသားပါ။", reply_markup=kb_reply_admin())
            _state[chat_id] = {}
            return
        add_allowed(target, "", uid)
        send_message(chat_id, f"✅ သူ့အသုံးပြုသူ <code>{target}</code> ကို ခွင့်ပြုစာရင်း ထည့်ပြီးပါပြီ။", reply_markup=kb_reply_admin())
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
            send_message(chat_id, "⚠️ <b>Telegram ID (ဂဏန်း)</b> ပို့ပါ (သို့) သူ့ message ကို reply ပြီး ပို့ပါ:", reply_markup=None)
            return
        remove_allowed(target)
        send_message(chat_id, f"✅ သူ့အသုံးပြုသူ <code>{target}</code> ကို ဖယ်လိုက်ပါပြီ။", reply_markup=kb_reply_admin())
        _state[chat_id] = {}
        return

    # ---------- COMMANDS ----------
    # ---------- REPLY BUTTON HANDLERS (message text matches a button label) ----------
    if text == "🔊 အသံထုတ်မည်":
        voices = list_voices(uid)
        note = f"သင်မှာ အသံ {len(voices)} ခု ရှိပါတယ်။" if voices else "<b>အသံ မရှိသေးပါ</b> — အရင်ထည့်ပေးပါ။"
        send_message(chat_id, f"<b>🔊 အသံထုတ်မည်</b>\n{note}\n\nအောက်မှာ သင့်အသံကို နှိပ်ပြီး စာသားပို့ပါ:",
                     reply_markup=kb_reply_generate(voices))
        if voices:
            _state[chat_id] = {"step": "waiting_voice_select"}
        else:
            _state[chat_id] = {}
        return
    if text == "🎤 ကျွန်တော့အသံများ":
        voices = list_voices(uid)
        note = f"သင်မှာ အသံ <b>{len(voices)}</b> ခု သိမ်းထားပါတယ်။" if voices else "အသံ မသိမ်းထားသေးပါ။"
        send_message(chat_id, f"<b>🎤 ကျွန်တော့အသံများ</b>\n{note}\n\nအောက်မှာ ရွေးပေးပါ:\n➕ အသံထည့်မည် — အသံအသစ်ထည့်မည်\n📋 အသံစာရင်းကြည့်မည် — သိမ်းထားတဲ့ အသံများ", reply_markup=kb_reply_voices())
        return
    if text == "⚙️ ဆောင်ရွက်ချက်များ":
        if uid == OWNER_ID:
            send_message(chat_id, "<b>⚙️ ဆောင်ရွက်ချက်များ (ပိုင်ရှင်)</b>\nပိုင်ရှင်ထိန်းချုပ်မှုများ:", reply_markup=kb_reply_admin())
        else:
            send_message(chat_id, "<b>⚙️ ဆောင်ရွက်ချက်များ</b>", reply_markup=kb_reply_main())
        return
    if text == "ဆက်သွယ်ရန် @Kmvclone":
        send_message(chat_id, "ပိုင်ရှင်နဲ့ ဆက်သွယ်ရန်: <b>@Kmvclone</b>\nhttps://t.me/Kmvclone", reply_markup=kb_reply_main())
        return
    if text == "➕ အသံထည့်မည်":
        send_message(chat_id, "ဒီအသံအတွက် <b>ဘယ်နာမည်</b> ပေးမလဲ? (ဥပမာ — myvoice)\nနာမည်ပို့ပြီးရင် <b>အသံ message (သို့) audio ဖိုင်</b> ပို့ပေးပါ:", reply_markup=None)
        _state[chat_id] = {"step": "waiting_name"}
        return
    if text == "📋 အသံစာရင်းကြည့်မည်":
        voices = list_voices(uid)
        if not voices:
            send_message(chat_id, " အသံ မသိမ်းထားသေးပါ။\nအောက်မှာ <b>➕ အသံထည့်မည်</b> ကိုနှိပ်ပြီး အသံ message ပို့ပေးပါ။", reply_markup=kb_reply_voices())
            return
        _state[chat_id] = {"step": "waiting_voice_select"}
        send_message(chat_id, "<b>သုံးမယ့် အသံကို ရွေးပေးပါ:</b>", reply_markup=kb_reply_select_voice(voices))
        return
    if text == "➕ အသုံးပြုသူထည့်မည်":
        if uid != OWNER_ID:
            send_message(chat_id, "⛔ ပိုင်ရှင်သီးသန့်ပါ။", reply_markup=kb_reply_main())
            return
        send_message(chat_id, "👤 သူ့ရဲ့ <b>Telegram ID (ဂဏန်း)</b> ပို့ပါ (သို့) သူ့ message ကို reply ပြီး ပို့ပါ:")
        _state[chat_id] = {"step": "waiting_adduser"}
        return
    if text == "➖ အသုံးပြုသူဖယ်မည်":
        if uid != OWNER_ID:
            send_message(chat_id, "⛔ ပိုင်ရှင်သီးသန့်ပါ။", reply_markup=kb_reply_main())
            return
        users = list_allowed()
        _state[chat_id] = {"step": "waiting_remuser"}
        send_message(chat_id, "<b>အောက်မှာ သူ့အသုံးပြုသူ ID ကို နှိပ်ပြီး ဖယ်ပါ</b>\n(သို့) ID ပို့ / reply ပြီးပို့လို့ရပါတယ်:",
                     reply_markup=kb_reply_remove(users))
        return
    if text == "📋 အသုံးပြုသူစာရင်း":
        if uid != OWNER_ID:
            send_message(chat_id, "⛔ ပိုင်ရှင်သီးသန့်ပါ။", reply_markup=kb_reply_main())
            return
        users = list_allowed()
        if not users:
            txt = " ပိုင်ရှင်အပြင် ခွင့်ပြုထားတဲ့ သူ မရှိသေးပါ။"
        else:
            txt = "\n".join(f" • <code>{u}</code> (@{n or '?'})" for u, n, _ in users)
        send_message(chat_id, f"<b>ခွင့်ပြုထားတဲ့ သူများ:</b>\n{txt}", reply_markup=kb_reply_admin())
        return
    if text == "🖥 Server အခြေအနေ":
        if uid != OWNER_ID:
            send_message(chat_id, "⛔ ပိုင်ရှင်သီးသန့်ပါ။", reply_markup=kb_reply_main())
            return
        ok = server_health()
        send_message(
            chat_id,
            f"<b>Server အခြေအနေ:</b> {'🟢 အောင်လိုင်' if ok else '🔴 အော့ဖ်လိုင်'}\n"
            f"URL: <code>{SERVER_URL}</code>",
            reply_markup=kb_reply_admin(),
        )
        return
    if text == "◀️ မူလစာမျက်နှာ":
        _state[chat_id] = {}
        send_message(chat_id, text_for(uid), reply_markup=kb_reply_main())
        return
    if text == "❌ ပယ်ဖြက်မည်":
        _state[chat_id] = {}
        send_message(chat_id, "❌ ပယ်ဖြက်ပြီးပါပြီ။", reply_markup=kb_reply_main())
        return

    # voice selection from the Generate / List Voices menus
    if st.get("step") == "waiting_voice_select":
        voices = list_voices(uid)
        names = [v[1] for v in voices]
        name = text.replace("🎙 ", "").strip() if text.startswith("🎙 ") else text
        if name in names:
            v = get_voice(uid, name)
            if not v:
                send_message(chat_id, "⚠️ အသံမရှိတော့ပါ — ထပ်ထည့်ပေးပါ။", reply_markup=kb_reply_voices())
                _state[chat_id] = {}
                return
            _state[chat_id] = {"step": "waiting_text", "voice_name": name}
            send_message(chat_id, f"✅ အသံ <b>{name}</b> ရွေးချဲ့ပြီးပါပြီ။\n\nယခု <b>အသံထုတ်ချင်တဲ့ စာသားကို ပို့ပေးပါ</b>:",
                         reply_markup=kb_reply([["❌ ပယ်ဖြက်မည်"]]))
            return
        return

    if st.get("step") == "waiting_remuser" and uid == OWNER_ID:
        # button label is the user's numeric id, or typed id
        if text.isdigit():
            target = int(text)
            remove_allowed(target)
            send_message(chat_id, f"✅ သူ့အသုံးပြုသူ <code>{target}</code> ကို ဖယ်လိုက်ပါပြီ။", reply_markup=kb_reply_admin())
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
            send_message(chat_id, "⚠️ အသံ မသိမ်းထားသေးပါ။\n<b>🎤 ကျွန်တော့အသံများ</b> → <b>➕ အသံထည့်မည်</b> အရင်လုပ်ပါ။", reply_markup=kb_reply_main())
            return
        voice = get_voice(uid, voices[0][1])
        if not voice:
            send_message(chat_id, "⚠️ သိမ္းထားတဲ့ reference အသံ မရှိတော့ပါ — ထပ်ထည့်ပေးပါ။", reply_markup=kb_reply_main())
            return
        start_r = send_message(chat_id, "🎙 အသံထုတ်နေပါတယ်...\n[▓▓▓▓▓▓▓▓▓▓] 0%")
        start_msg_id = (start_r.get("result") or {}).get("message_id")
        wav, err = generate_voice(args.strip(), voice[3], chat_id=chat_id, start_msg_id=start_msg_id)
        if err:
            send_message(chat_id, f"⚠️ မအောင်မြင်:\n{err}", reply_markup=kb_reply_main())
            return
        send_voice(chat_id, wav, caption=f"{BOT_NAME} — အသံ: {voice[2]}", reply_markup=kb_reply_main())
        return

    if cmd in ("/voice",) and not args.strip():
        send_message(chat_id, "အသံရွေးပြီးနောက် <b>/voice စာသား</b> ပို့ပါ (<b>🎤 ကျွန်တော့အသံများ</b> မှာ)။", reply_markup=kb_reply_main())
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
            "ℹ️ စာသားသီးသန့်ဆိုရင် အသံမထုတ်ပေးပါ။\n"
            "ပြီးရင် <b>🎤 ကျွန်တော့အသံများ</b> → အသံထည့် → <b>🔊 အသံထုတ်မည်</b> ကိုသုံးပါ။",
            reply_markup=kb_reply_main(),
        )
        return


# ---------------- POLL LOOP ----------------

def poll(offset: int, timeout: int = 30):
    return api("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]}, timeout=timeout + 10)


# ---------------- GITHUB ACTIONS MODE ----------------
# Run with: RUN_MODE=github python3 bot.py
# One-shot: process all pending updates once, then exit. Used by scheduled GH Action.
# Default (RUN_MODE=persistent): long-poll loop forever.
def _run_mode():
    return os.environ.get("RUN_MODE", "persistent")


def run():
    if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_"):
        print("ERROR: set BOT_TOKEN, SERVER_URL, OWNER_ID at the top of this file")
        raise SystemExit(1)
    mode = _run_mode()
    print(f"[{BOT_NAME}] starting... (owner={OWNER_ID}, mode={mode})")
    print(f"[{BOT_NAME}] server: {SERVER_URL}")
    if not server_health(timeout=15):
        print(f"[{BOT_NAME}] WARNING: server health check failed — check SERVER_URL")
    offset = 0
    while True:
        try:
            r = poll(offset)
        except Exception as e:
            print(f"[{BOT_NAME}] poll error: {e}; retrying in 5s")
            if mode == "github":
                return
            time.sleep(5)
            continue
        if not r.get("ok"):
            print(f"[{BOT_NAME}] api error: {r.get('description')}; retrying in 5s")
            if mode == "github":
                return
            time.sleep(5)
            continue
        updates = r.get("result", [])
        if not updates:
            if mode == "github":
                print(f"[{BOT_NAME}] no pending updates — done")
                return
        for upd in updates:
            offset = max(offset, upd.get("update_id", 0) + 1)
            try:
                handle_message(upd)
            except Exception as e:
                print(f"[{BOT_NAME}] handler error: {e}")
        if mode == "github":
            print(f"[{BOT_NAME}] processed {len(updates)} updates — done")
            return
        time.sleep(0.2)


if __name__ == "__main__":
    run()
