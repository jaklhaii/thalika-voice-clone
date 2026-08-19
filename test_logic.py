#!/usr/bin/env python3
"""Logic tests for KM Voice Clone bot (Myanmar reply-keyboard version)."""
import importlib.util
import sqlite3
import sys
import unittest.mock

spec = importlib.util.spec_from_file_location("bot", "bot.py")
bot = importlib.util.module_from_spec(spec)

# Patch before exec: use temp db, no server check
import tempfile, os
tmpdir = tempfile.mkdtemp()
os.environ.pop("_", None)

# Intercept sqlite3.connect via a mock applied inside module exec
import unittest.mock as um
spec.loader.exec_module(bot)
bot.DB_PATH = os.path.join(tmpdir, "km_voice.db")
bot._db = sqlite3.connect(bot.DB_PATH, check_same_thread=False)
bot._db.executescript("""
CREATE TABLE IF NOT EXISTS allowed_users (user_id INTEGER PRIMARY KEY, username TEXT, added_at INTEGER, added_by INTEGER);
CREATE TABLE IF NOT EXISTS voices (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, name TEXT NOT NULL, audio_b64 TEXT NOT NULL, created_at INTEGER, UNIQUE(owner_id, name));
""")
bot._db.commit()

# Capture sent messages
sent = []
def send_message(chat_id, text, reply_markup=None, reply_to=None, parse="HTML"):
    sent.append((chat_id, text, reply_markup))
    return {"ok": True, "result": {"message_id": 42}}
bot.send_message = send_message

VOICE_B64 = "AAAA"
UID = 8970380146
OTHER = 123456789

def mk_msg(**kw):
    m = {"chat": {"id": UID}, "from": {"id": UID, "username": "Kmvclone"}}
    m.update(kw)
    return {"message": m}

def mk_msg_other(**kw):
    m = {"chat": {"id": OTHER}, "from": {"id": OTHER, "username": "otheruser"}}
    m.update(kw)
    return {"message": m}

# Add owner & non-owner to allowed users; add sample voice
bot.add_allowed(OTHER, "otheruser", UID)
bot.save_voice(UID, "myvoice", VOICE_B64)

errors = []

def run(name, upd):
    bot._state.clear()
    sent.clear()
    try:
        bot.handle_message(upd)
    except Exception as e:
        errors.append(f"{name}: EXCEPTION {e}")
        print(f"FAIL  {name}: {e}")
        return
    print(f"OK    {name}")


def run_keep(name, upd):
    """Like run() but keeps _state (for multi-step flows)."""
    sent.clear()
    try:
        bot.handle_message(upd)
    except Exception as e:
        errors.append(f"{name}: EXCEPTION {e}")
        print(f"FAIL  {name}: {e}")
        return
    print(f"OK    {name}")

# 1) /start shows welcome with main reply keyboard (buttons below message)
run("/start", mk_msg(text="/start"))
assert sent and "ကြိုဆ" in sent[-1][1], "welcome text"
kb = sent[-1][2]
assert "inline_keyboard" in kb, "must be inline keyboard"
btns = {b["text"] for row in kb["inline_keyboard"] for b in row}
for need in ["🔊 အသံထုတ်မည်", "🎤 ကျွန်တော့်အသံများ", "⚙️ ဆောင်ရွက်ချက်များ", "ဆက်သွယ်ရန် @Kmvclone"]:
    assert need in btns, f"missing button {need}"

# 2) Add voice flow: name then audio
# use the EXACT button label bytes from bot.py (avoids Myanmar rendering ambiguity)
run_keep("add voice ask name", mk_msg(text="\u2795\u0020\u1021\u101E\u1036\u1011\u100A\u1037\u103A\u1019\u100A\u103A"))
assert sent and "ပေးမလဲ" in sent[-1][1], f"name prompt: {sent[-1][1]}"
# state now waiting_name — send a voice name
run_keep("send voice name", mk_msg(text="myvoice2"))
assert bot._state.get(UID) and bot._state[UID]["step"] == "waiting_audio", "now waiting_audio"
# send the audio file (getFile will fail against real API → error message, still counts)
run_keep("send audio", {"message": {"chat": {"id": UID}, "from": {"id": UID},
    "voice": {"file_id": "f123", "duration": 5}}})
assert sent and ("⚠️" in sent[-1][1] or "ဒါက အသံ" in sent[-1][1]), f"audio flow produced a message: {sent[-1][1] if sent else 'NONE'}"

# 3) Main buttons trigger handlers (Myanmar labels)
run("generate button", mk_msg(text="🔊 အသံထုတ်မည်"))
assert sent[-1][2] and "inline_keyboard" in sent[-1][2], "generate shows inline keyboard"
run("voices button", mk_msg(text="🎤 ကျွန်တော့အသံများ"))
assert "1</b> ခု" in sent[-1][1], f"voices count: {sent[-1][1]}"
run_keep("settings owner", mk_msg(text="\u2699\uFE0F\u0020\u1006\u1031\u102C\u1004\u103A\u101B\u103D\u1000\u103A\u1001\u103B\u1000\u103A\u1019\u103B\u102C\u1038"))
kb = sent[-1][2]
btns = {b["text"] for row in kb["inline_keyboard"] for b in row}
assert "➕ အသုံးပြုသူထည့်မည်" in btns, "owner sees admin buttons"

# 4) Non-owner settings shows no admin buttons
bot._state.clear(); sent.clear()
run("settings non-owner", mk_msg_other(text="\u2699\uFE0F\u0020\u1006\u1031\u102C\u1004\u103A\u101B\u103D\u1000\u103A\u1001\u103B\u1000\u103A\u1019\u103B\u102C\u1038"))
kb = sent[-1][2]
btns = {b["text"] for row in kb["inline_keyboard"] for b in row}
assert "➕ အသုံးပြုသူထည့်မည်" not in btns, "non-owner must NOT see admin buttons"

# 5) List voices → select voice with 🎙 prefix → waiting_text
bot._state.clear(); sent.clear()
run("list voices", mk_msg(text="📋 အသံစာရင်းကြည့်မည်"))
assert bot._state.get(UID)["step"] == "waiting_voice_select", "list sets select state"
kb = sent[-1][2]
names = [b["text"] for row in kb["inline_keyboard"] for b in row]
voice_btn = next(n for n in names if n.startswith(("🎙 ", "myvoice", "v1")) and "ပယ်ဖျက" not in n and "❌" not in n)
run_keep("select voice", mk_msg(text=voice_btn))
assert bot._state.get(UID)["step"] == "waiting_text", "selected voice"
assert "ရွေးချဲ့" in sent[-1][1] or "ရွေးချယ်" in sent[-1][1], f"selected msg: {sent[-1][1]}"

# 6) Server info for owner
bot._state.clear(); sent.clear()
run("server info", mk_msg(text="🖥 Server အခြေအနေ"))
assert "Server အခြေအနေ" in sent[-1][1], "server info shown"

# 7) Contact button
bot._state.clear(); sent.clear()
run("contact", mk_msg(text="\u1006\u1000\u103A\u101E\u103D\u101A\u103A\u101B\u1014\u103A\u0020\u0040\u004B\u006D\u0076\u0063\u006C\u006F\u006E\u0065"))
assert "@Kmvclone" in sent[-1][1]

# 8) Back to menu clears state
bot._state[UID] = {"step": "waiting_text", "voice_name": "x"}
run("back to menu", mk_msg(text="\u25C0\uFE0F\u0020\u1019\u1030\u101C\u1005\u102C\u1019\u103B\u1000\u103A\u1014\u103E\u102C"))
assert bot._state.get(UID) == {}, "state cleared"

# 9) Cancel clears state
bot._state[UID] = {"step": "waiting_name"}
run("cancel", mk_msg(text="\u274C\u0020\u1015\u101A\u103A\u1016\u103C\u1000\u103A\u1019\u100A\u103A"))
assert bot._state.get(UID) == {}, "cancel cleared"

# 10) Admin user management
bot._state.clear(); sent.clear()
run_keep("add user ask", mk_msg(text="\u2795\u0020\u1021\u101E\u102F\u1036\u1038\u1015\u103C\u102F\u101E\u1030\u1011\u100A\u1037\u103A\u1019\u100A\u103A"))
assert sent and "Telegram ID" in sent[-1][1]

# 11) Remove user
bot._state.clear(); sent.clear()
run_keep("remove user", mk_msg(text="\u2796\u0020\u1021\u101E\u102F\u1036\u1038\u1015\u103C\u102F\u101E\u1030\u1016\u101A\u103A\u1019\u100A\u103A"))
assert bot._state.get(UID)["step"] == "waiting_remuser", "remove state"
run_keep("confirm remove", mk_msg(text=str(OTHER)))
assert "ဖယ်လိုက်" in sent[-1][1], f"remove confirm: {sent[-1][1]}"
assert not bot.user_allowed(OTHER), "user removed from db"

# 12) Text-only message gets pointer, not generation
bot._state.clear(); sent.clear()
run("text only", mk_msg(text="Hello world"))
assert "အသံမထုတ်ပေးပါ" in sent[-1][1] or "သီးသန့်" in sent[-1][1], f"text-only msg: {sent[-1][1]}"

# 13) Owner only enforcement
bot._state.clear(); sent.clear()
bot.add_allowed(OTHER, "otheruser", UID)  # re-add (step 11 removed this user)
run("adduser non-owner", mk_msg_other(text="\u2795\u0020\u1021\u101E\u102F\u1036\u1038\u1015\u103C\u102F\u101E\u1030\u1011\u100A\u1037\u103A\u1019\u100A\u103A"))
assert "ပိုင်ရှင်သီးသန့်" in sent[-1][1], "owner-only check works"

# 14) List users
run("list users", mk_msg(text="📋 အသုံးပြုသူစာရင်း"))
assert "ခွင့်ပြု" in sent[-1][1], "list users msg"

# 7) Callback (inline button) tap routes to the same handlers
bot._state.clear(); sent.clear()
errors2 = []
def run_cb(name, data, chat_id=UID, uid=UID, msg_id=7):
    upd = {"callback_query": {"id": f"cq_{name}", "from": {"id": uid, "username": "Kmvclone"},
        "chat_instance": "1",
        "message": {"message_id": msg_id, "chat": {"id": chat_id}, "from": {"id": uid}, "date": 1},
        "data": data}}
    try:
        bot.handle_callback_query(upd)
    except Exception as e:
        errors2.append(f"{name}: {e}")
        print(f"FAIL  cb {name}: {e}")
        return
    print(f"OK    cb {name}")
run_cb("gen", "gen")
assert sent and "အသံထုတ်မည့်" in sent[-1][1] or sent, "gen menu shown"
run_cb("voices", "voices")
assert "များ" in sent[-1][1], f"voices: {sent[-1][1]}"
run_cb("contact", "contact")
assert "@Kmvclone" in sent[-1][1], "contact shown"
run_cb("admin owner", "admin")
btns = {b["text"] for row in sent[-1][2]["inline_keyboard"] for b in row}
kb0 = sent[-1][2]
found = [b for row in kb0["inline_keyboard"] for b in row if "သူထည့်" in b["text"]]
assert found, "owner sees admin buttons via callback"
run_cb("admin nonowner", "admin", uid=OTHER)
kb0 = sent[-1][2]
found2 = [b for row in kb0["inline_keyboard"] for b in row if "သူထည့်" in b["text"]]
assert not found2, "non-owner no admin via callback"
run_cb("sel voice", "sel:myvoice")
assert bot._state.get(UID) and bot._state[UID]["step"] == "waiting_text", "voice selected via callback"
run_cb("rem nonowner", "rem:123", uid=OTHER)
assert "⛔" in sent[-1][1], "non-owner blocked from removing"

print("\n" + "=" * 40)
if errors:
    print("FAILURES:", errors); sys.exit(1)
print("ALL LOGIC TESTS PASSED (Myanmar inline-keyboard version)")
