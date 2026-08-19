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
import hashlib
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request

# ---------------- CONFIG ----------------
BOT_TOKEN = "8924460807:AAGBGV2X6iQqj5P-pRayjKpm5r_tmM8a7jo"
SERVER_URL = ""  # external voice server URL (empty => GitHub-only queue mode)
OWNER_ID = 8970380146

# GitHub-only generation queue mode:
# text+reference jobs are committed to scripts/ghq/pending/ in this repo.
# The GitHub Action runs the CPU worker (GGUF VoxCPM2, ~3.3GB, CPU) which
# writes scripts/ghq/done/{job_id}.json; the bot picks it up next run and
# sends the voice message. Requires GEN_MODE=github env (set in bot.yml).
GEN_MODE = os.environ.get("GEN_MODE", "server")  # "server" | "github"

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

def _audit(method: str, raw: bytes) -> None:
    """Append one audit line per Telegram API call (for GitHub Actions debugging)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gh_api_audit.log"), "a") as f:
            f.write("%d|%s|%s\n" % (int(time.time()), method, raw[:300].decode(errors="replace").replace("\n", " ")))
    except Exception:
        pass


def api(method: str, payload: dict, timeout: int = 30):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            _audit(method, raw)
            if not raw:
                return {"ok": False, "description": f"empty body HTTP {resp.status}"}
            return json.loads(raw.decode())
    except Exception as e:
        body = b""
        try:
            body = e.read()[:400]
        except Exception:
            pass
        _audit(method, b"ERROR: " + body + b" | " + str(e).encode()[:120])
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
    if reply_markup is None:
        reply_markup = kb_reply_main()
    payload["reply_markup"] = reply_markup
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    return api("sendMessage", payload)


def _ikb(rows):
    """InlineKeyboardMarkup — callback buttons attached below each message."""
    return {"inline_keyboard": rows}


def kb_reply_main():
    return _ikb([
        [{"text": "🔊 အသံထုတ်မည်", "callback_data": "gen"}, {"text": "🎤 ကျွန်တော့်အသံများ", "callback_data": "voices"}],
        [{"text": "⚙️ ဆောင်ရွက်ချက်များ", "callback_data": "admin"}, {"text": "ဆက်သွယ်ရန် @Kmvclone", "callback_data": "contact"}],
    ])


def kb_reply_voices():
    return _ikb([[{"text": "➕ အသံထည့်မည်", "callback_data": "voices_add"}, {"text": "📋 အသံစာရင်းကြည့်မည်", "callback_data": "voices_list"}], [{"text": "◀️ မူလစာမျက်နှာ", "callback_data": "main"}]])


def kb_reply_generate(voices):
    rows = [[{"text": f"🎙 {v[1]}", "callback_data": f"sel:{v[1]}"} for v in voices]] if voices else []
    rows.append([{"text": "◀️ မူလစာမျက်နှာ", "callback_data": "main"}])
    return _ikb(rows)


def kb_reply_admin():
    return _ikb([
        [{"text": "➕ အသုံးပြုသူထည့်မည်", "callback_data": "adduser"}, {"text": "➖ အသုံးပြုသူဖယ်မည်", "callback_data": "remuser"}],
        [{"text": "📋 အသုံးပြုသူစာရင်း", "callback_data": "listusers"}, {"text": "🖥 Server အခြေအနေ", "callback_data": "server"}],
        [{"text": "◀️ မူလစာမျက်နှာ", "callback_data": "main"}],
    ])


def kb_reply_remove(users):
    rows = [[{"text": str(uid), "callback_data": f"rem:{uid}"} for uid, _u, _t in users]] if users else []
    rows.append([{"text": "◀️ နောက်ကျပြန်", "callback_data": "admin"}])
    return _ikb(rows)


def kb_reply_select_voice(voices):
    rows = [[{"text": v[1], "callback_data": f"sel:{v[1]}"} for v in voices]] if voices else []
    rows.append([{"text": "❌ ပယ်ဖြက်မည်", "callback_data": "cancel"}])
    return _ikb(rows)


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


def _server_post(path: str, payload_bytes, timeout: int = 30):
    """POST JSON to the server; return parsed dict."""
    req = urllib.request.Request(
        f"{SERVER_URL}{path}", data=payload_bytes, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _server_get(path: str, timeout: int = 30):
    """GET from the server; return parsed dict."""
    req = urllib.request.Request(f"{SERVER_URL}{path}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def generate_voice(text: str, reference_b64: str, style: str = None, chat_id=None,
                   start_msg_id=None, timeout: int = 600):
    """Call the Colab server (async job mode) or generate locally if SERVER_URL is empty."""
    if not SERVER_URL:
        return generate_voice_local(text, reference_b64, chat_id=chat_id,
                                    start_msg_id=start_msg_id, timeout=timeout)
    payload = json.dumps({"text": text, "audio": reference_b64, "style": style}).encode()
    start = time.time()
    try:
        job = _server_post("/generate", payload, timeout=30)
    except urllib.error.HTTPError as e:
        return None, f"Server error {e.code}: {e.read().decode(errors='replace')[:200]}"
    except Exception as e:
        return None, f"Connection error: {e}"
    if isinstance(job, dict) and "error" in job:
        return None, job.get("error", "Server error")
    job_id = job.get("job_id") if isinstance(job, dict) else None
    if not job_id:
        # legacy sync response (audio embedded) handled as before
        result = job
        job_id = None
    else:
        result = None

    pct = 0
    last_pct = -1
    last_update = 0
    if not job_id:
        return None, "Server did not return a job id"

    while time.time() - start < timeout:
        try:
            st = _server_get(f"/result/{job_id}", timeout=15)
        except Exception as e:
            time.sleep(3)
            continue
        if not isinstance(st, dict):
            time.sleep(3)
            continue
        if st.get("status") == "running":
            # progress update every 10s (max 90%)
            est = min(90, int((time.time() - start) / 8.0))
            est = max(est, pct)
            now = time.time()
            if est - last_pct >= 10 and chat_id is not None and now - last_update > 8:
                last_update = now
                last_pct = est
                pct = est
                api("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": start_msg_id,
                    "text": f" Generating your cloned voice...\n[{_progress_bar(pct)}] {pct}%",
                    "parse_mode": "HTML",
                })
            time.sleep(4)
            continue
        if "error" in st:
            return None, st.get("error", "Generation failed")
        if "audio" in st:
            result = st
            break
        time.sleep(2)
    else:
        return None, "Generation timed out (server may be overloaded)"

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


# ---------------- GITHUB QUEUE (GEN_MODE=github) ----------------
# Repo: jaklhaii/thalika-voice-clone, branch main. Uses GITHUB_TOKEN env
# (auto-provided by GitHub Actions) to push job files via the Contents API.

def _gh_repo():
    owner_repo = os.environ.get("GH_REPO", "jaklhaii/thalika-voice-clone")
    return os.environ.get("GH_TOKEN", ""), owner_repo


def _gh_api(method: str, path: str, body=None, base64_content=None, timeout: int = 60):
    """GitHub REST API call (Contents API for repo files). Returns parsed JSON dict."""
    token, repo = _gh_repo()
    url = f"https://api.github.com/repos/{repo}/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    elif base64_content is not None:
        data = json.dumps({"message": "km voice clone job", "content": base64_content, "branch": "main"}).encode()
    else:
        data = None
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode(errors="replace")[:300]}, e.code
    except Exception as e:
        return {"error": str(e)}, 0


def _queue_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "ghq")


def _queue_put(path_in_repo: str, content: bytes, commit_msg: str) -> bool:
    """PUT file content into the repo via Contents API (b64 content object)."""
    body = {"message": commit_msg, "content": base64.b64encode(content).decode(), "branch": "main"}
    res, status = _gh_api("PUT", f"contents/{path_in_repo}", body=body)
    if status not in (200, 201):
        print(f"[queue] PUT {path_in_repo} failed: {res.get('error')}", flush=True)
        return False
    return True


def _queue_get(path_in_repo: str):
    """GET file from repo; returns (bytes, sha) or (None, None)."""
    res, status = _gh_api("GET", f"contents/{path_in_repo}?ref=main")
    if status != 200 or not isinstance(res, dict):
        return None, None
    return base64.b64decode(res["content"]), res.get("sha")


def _queue_delete(path_in_repo: str, sha: str) -> bool:
    body = {"message": "km voice clone cleanup", "sha": sha, "branch": "main"}
    res, status = _gh_api("DELETE", f"contents/{path_in_repo}", body=body)
    return status in (200, 202)


def _pending_path(job_id: str) -> str:
    return f"scripts/ghq/pending/{job_id}.json"


def _done_path(job_id: str) -> str:
    return f"scripts/ghq/done/{job_id}.json"


def _queue_submit_job(user_id: int, chat_id: int, start_msg_id, text: str, voice_name: str) -> str:
    job_id = hashlib.md5(f"{user_id}:{chat_id}:{text}:{voice_name}:{time.time()}".encode()).hexdigest()[:16]
    job = {
        "job_id": job_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "start_msg_id": start_msg_id,
        "text": text,
        "voice_name": voice_name.strip().lower(),
        "ts": int(time.time()),
    }
    _queue_put(_pending_path(job_id), json.dumps(job).encode(), f"voice job {job_id}")
    return job_id


def _queue_save_ref(owner_id: int, voice_name: str, audio_b64: str) -> bool:
    wav = base64.b64decode(audio_b64)
    name = voice_name.strip().lower()
    return _queue_put(f"scripts/ghq/refs/{owner_id}_{name}.wav", wav, f"voice ref {owner_id}/{name}")


def _queue_pickup_done() -> list:
    """Scan scripts/ghq/done/ for finished jobs, download and return list of dicts."""
    token, repo = _gh_repo()
    url = f"https://api.github.com/repos/{repo}/contents/scripts/ghq/done?ref=main"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            files = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[queue] scan done/ failed: {e}", flush=True)
        return []
    if not isinstance(files, list):
        return []
    out = []
    for entry in files:
        if not entry.get("name", "").endswith(".json"):
            continue
        b, sha = _queue_get(f"scripts/ghq/done/{entry['name']}")
        if not b:
            continue
        try:
            job = json.loads(b.decode())
        except Exception:
            _queue_delete(f"scripts/ghq/done/{entry['name']}", sha)
            continue
        job["_sha"] = sha
        job["_file"] = entry["name"]
        out.append(job)
    return out


def generate_voice_queue(text: str, reference_b64: str, voice_name: str,
                         user_id: int, chat_id: int, start_msg_id) -> tuple:
    """GitHub-only mode: commit ref + job, return (job_id_or_None, error)."""
    name = voice_name.strip().lower()
    if not _queue_save_ref(user_id, name, reference_b64):
        return None, "reference file upload failed"
    if api("editMessageText", {
        "chat_id": chat_id, "message_id": start_msg_id,
        "text": ("🎙 <b>အသံထုတ်မည့်အလုပ်</b> GitHub runner queue ထဲ ထည့်ပြီးပါပီ။\n"
                 "⚠️ Free runner (2-core CPU) ဖြစ်လို့ <b>၁၀–၂၀ မိနစ်</b> ကြာနိုင်ပါတယ်။\n"
                 "ပြီးရင် bot က အလိုအလျောက် အသံပြန်ပို့ပေးပါမယ်။\n\n"
                 "(အသံရောင်းဖိုင် scripts/ghq/pending/ ထဲမှာ စောင့်နေပါတယ်)"),
        "parse_mode": "HTML",
    }).get("ok") is not True:
        api("sendMessage", {
            "chat_id": chat_id, "reply_to_message_id": start_msg_id,
            "text": ("🎙 အလုပ် queue ထဲ ထည့်ပြီးပါပီ — ၁၀–၂၀ မိနစ် ကြာနိုင်ပါတယ်၊ "
                     "ပြီးရင် အလိုအလျောက် ပြန်ပို့ပေးပါမယ်။"),
        })
    job_id = _queue_submit_job(user_id, chat_id, start_msg_id, text, voice_name)
    return job_id, None


def deliver_queued_voices() -> int:
    """Send finished voice jobs from scripts/ghq/done/; return count delivered."""
    n = 0
    for job in _queue_pickup_done():
        job_id = job.get("job_id", "?")
        chat_id = job.get("chat_id")
        if not chat_id:
            continue
        if "error" in job:
            api("sendMessage", {
                "chat_id": chat_id,
                "text": f"⚠️ အသံထုတ်မှု မအောင်မြင်ပါ (job {job_id}):\n{job['error']}",
                "reply_markup": kb_reply_main(),
            })
        else:
            try:
                wav = base64.b64decode(job["wav_b64"])
            except Exception:
                api("sendMessage", {"chat_id": chat_id, "text": "⚠️ အသံဖိုင် ဖတ်လို့မရပါ — ထပ်ကြိုးစားကြည့်ပါ။", "reply_markup": kb_reply_main()})
            else:
                cap = f"{BOT_NAME} — {job.get('duration_s', '?')}s @48kHz"
                api("sendMessage", {"chat_id": chat_id, "text": f"✅ အသံထုတ်ပြီးပါပီ ({job.get('duration_s', '?')} စကကန့်)", "reply_markup": kb_reply_main()})
                api_file("sendVoice", {"voice": ("voice.wav", "audio/wav", wav)}, {"chat_id": chat_id, "caption": cap})
        _queue_delete(f"scripts/ghq/done/{job['_file']}", job["_sha"])
        n += 1
    return n


def server_health(timeout: int = 10):
    if not SERVER_URL:
        return True  # local in-process mode: no external server needed
    try:
        url = f"{SERVER_URL}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _local_job_dir():
    return "/tmp"


def generate_voice_local(text: str, reference_b64: str, chat_id=None,
                         start_msg_id=None, timeout: int = 900):
    """Local in-process mode: run VoxCPM2 via local_gen_worker.py in sandbox.
    Spawns worker subprocess, polls /tmp/kmgen_{job_id}.out.json with progress."""
    import subprocess
    import sys as _sys
    job_id = f"{int(time.time() * 1000)}_{chat_id or 0}"
    job_dir = _local_job_dir()
    ref_path = os.path.join(job_dir, f"kmref_{job_id}.wav")
    try:
        raw = base64.b64decode(reference_b64)
        with open(ref_path, "wb") as f:
            f.write(raw)
    except Exception as e:
        return None, f"reference decode error: {e}"
    job_path = os.path.join(job_dir, f"kmgen_{job_id}.json")
    with open(job_path, "w") as f:
        json.dump({"job_id": job_id, "text": text, "ref_wav": ref_path, "style": None}, f)
    out_path = os.path.join(job_dir, f"kmgen_{job_id}.out.json")
    # remove stale out file
    if os.path.exists(out_path):
        os.unlink(out_path)
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "local_gen_worker.py")
    try:
        subprocess.Popen(
            [_sys.executable, worker, job_id],
            stdout=open(os.path.join(job_dir, f"kmgen_{job_id}.log"), "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        return None, f"worker launch error: {e}"
    start = time.time()
    last_pct = -1
    loading_warned = False
    while time.time() - start < timeout:
        if not os.path.exists(out_path):
            now = time.time()
            if now - start > 30 and not loading_warned:
                loading_warned = True
                api("sendMessage", {
                    "chat_id": chat_id,
                    "text": "⏳ VoxCPM2 model (~9 GB) ကို ပထမအကြိမ် ဒေါင်လုဒ်လုပ်နေပါတယ — <b>၁၀–၂၀ မိနစ်</b> ကြာနိုင်ပါတယ်။ နောက်တစ်ခါကစ ပိုမြန်ပါမယ်။",
                    "parse_mode": "HTML",
                })
            time.sleep(5)
            continue
        try:
            with open(out_path) as f:
                st = json.load(f)
        except Exception:
            time.sleep(3)
            continue
        status = st.get("status")
        if status == "running":
            pct = max(5, int(min(90, 5 + (time.time() - start) / 6.0)))
            now = time.time()
            if pct - last_pct >= 10 and chat_id is not None:
                last_pct = pct
                api("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": start_msg_id,
                    "text": f"🎙 Clone အသံ ထုတ်နေပါတယ...\n[{_progress_bar(pct)}] {pct}%",
                    "parse_mode": "HTML",
                })
            time.sleep(5)
            continue
        if status == "error":
            return None, st.get("error") or "worker error"
        if status == "done" and st.get("audio"):
            # final 100% update
            if chat_id is not None:
                api("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": start_msg_id,
                    "text": f"🎙 Clone အသံ ထုတ်နေပါတယ...\n[{_progress_bar(100)}] 100%",
                    "parse_mode": "HTML",
                })
            try:
                wav = base64.b64decode(st["audio"])
            except Exception:
                return None, "Failed to decode generated audio"
            # cleanup
            for p in (ref_path, job_path, out_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass
            return wav, None
        time.sleep(3)
    return None, "Generation timed out"


# ---------------- KEYBOARDS (ReplyKeyboardMarkup — buttons below message) ----------------


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
        if GEN_MODE == "github":
            job_id, err = generate_voice_queue(text, voice[3], voice[2], uid, chat_id, start_msg_id)
            if err:
                send_message(chat_id, f"⚠️ အသံထုတ်မှု မအောင်မြင်:\n{err}", reply_markup=kb_reply_main())
            _state[chat_id] = {}
            return
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
                         reply_markup=_ikb([[{"text": "❌ ပယ်ဖြတ်မည်", "callback_data": "cancel"}]]))
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
        if GEN_MODE == "github":
            job_id, err = generate_voice_queue(args.strip(), voice[3], voice[2], uid, chat_id, start_msg_id)
            if err:
                send_message(chat_id, f"⚠️ မအောင်မြင်:\n{err}", reply_markup=kb_reply_main())
            return
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
    try:
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gh_poll_last.json"), "w").write(str(offset))
    except Exception:
        pass
    return api("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]}, timeout=timeout + 10)


# ---------------- GITHUB ACTIONS MODE ----------------
# Run with: RUN_MODE=github python3 bot.py
# One-shot: process all pending updates once, then exit. Used by scheduled GH Action.
# Default (RUN_MODE=persistent): long-poll loop forever.
def _run_mode():
    return os.environ.get("RUN_MODE", "persistent")



def handle_callback_query(update: dict):
    """Route inline button taps (callback_query) to the same button logic as plain text taps."""
    cq = update.get("callback_query")
    if not cq:
        return
    cid = cq["id"]
    chat_id = cq["message"]["chat"]["id"]
    uid = cq["from"]["id"]
    data = (cq.get("data") or "").strip()

    def answer(text=None):
        r = api("answerCallbackQuery", {"callback_query_id": str(cid), "text": text} if text else {"callback_query_id": str(cid)})
        if isinstance(r, dict) and not r.get("ok"):
            print("[answerCallbackQuery failed]", r.get("description"))

    answer()
    if not user_allowed(uid):
        return

    def as_message_button(txt):
        # replay the tapped label through handle_message so all button logic is shared
        upd = {"message": {"message_id": cq["message"]["message_id"],
                           "from": cq["from"], "chat": cq["message"]["chat"],
                           "date": cq.get("message", {}).get("date", 0), "text": txt}}
        handle_message(upd)

    if data == "gen":
        as_message_button("🔊 အသံထုတ်မည်")
    elif data == "voices":
        as_message_button("🎤 ကျွန်တော့အသံများ")
    elif data == "voices_add":
        as_message_button("➕ အသံထည့်မည်")
    elif data == "voices_list":
        as_message_button("📋 အသံစာရင်းကြည့်မည်")
    elif data == "admin":
        as_message_button("⚙️ ဆောင်ရွက်ချက်များ")
    elif data == "contact":
        as_message_button("ဆက်သွယ်ရန် @Kmvclone")
    elif data == "main":
        as_message_button("◀️ မူလစာမျက်နှာ")
    elif data == "cancel":
        as_message_button("❌ ပယ်ဖြက်မည်")
    elif data == "adduser":
        as_message_button("➕ အသုံးပြုသူထည့်မည်")
    elif data == "remuser":
        as_message_button("➖ အသုံးပြုသူဖယ်မည်")
    elif data == "listusers":
        as_message_button("📋 အသုံးပြုသူစာရင်း")
    elif data == "server":
        as_message_button("🖥 Server အခြေအနေ")
    elif data.startswith("sel:"):
        name = data[4:]
        as_message_button(f"🎙 {name}")
    elif data.startswith("rem:"):
        target = data[4:]
        if target.isdigit() and uid == OWNER_ID:
            remove_allowed(int(target))
            send_message(chat_id, f"✅ သူ့အသုံးပြုသူ <code>{target}</code> ကို ဖယ်လိုက်ပါပြီ။", reply_markup=kb_reply_admin())
            _state[chat_id] = {}
        else:
            send_message(chat_id, "⛔ ပိုင်ရှင်သီးသန့်ပါ။", reply_markup=kb_reply_main())
    else:
        return


def run():
    if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_"):
        print("ERROR: set BOT_TOKEN, SERVER_URL, OWNER_ID at the top of this file")
        raise SystemExit(1)
    mode = _run_mode()
    print(f"[{BOT_NAME}] starting... (owner={OWNER_ID}, mode={mode}, gen_mode={GEN_MODE})")
    print(f"[{BOT_NAME}] server: {SERVER_URL or '(none — GitHub queue mode)'}")
    if GEN_MODE == "github":
        token, repo = _gh_repo()
        print(f"[{BOT_NAME}] github queue: repo={repo} token={'ok' if token else 'MISSING!'}")
        # deliver finished jobs first
        try:
            done_n = deliver_queued_voices()
            print(f"[{BOT_NAME}] delivered {done_n} finished job(s)")
        except Exception as e:
            print(f"[{BOT_NAME}] pickup error: {e}")
    elif SERVER_URL and not server_health(timeout=15):
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
                if upd.get("callback_query"):
                    handle_callback_query(upd)
                else:
                    handle_message(upd)
            except Exception as e:
                print(f"[{BOT_NAME}] handler error: {e}")
        if mode == "github":
            print(f"[{BOT_NAME}] processed {len(updates)} updates — done")
            return
        time.sleep(0.2)


if __name__ == "__main__":
    run()
