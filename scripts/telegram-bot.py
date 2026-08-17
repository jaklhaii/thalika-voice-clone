"""
Thalika Telegram voice bot (GitHub Actions long-poll mode).

Commands (sent to the bot in chat):
    /voice <script>                    -> generate speech (voice design)
    /voice <control> | <script>        -> controllable cloning with style text

Reply to any voice message with "/voice <script>" to clone THAT voice
(the replied audio becomes the reference).

Runs until 4 hours of silence (Actions 6h limit guard) or when
TG_EXIT_AFTER_IDLE seconds of idle pass. Set TG_ONE_SHOT=1 to exit after
serving exactly one request (for "once" mode).
"""
import os
import random
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import json

TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("TG_BOT_TOKEN secret is not set.")

BOT_API = f"https://api.telegram.org/bot{TOKEN}"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOXCPM_SCRIPT = os.path.join(BASE, "scripts", "voxcpm-generate.py")

EXIT_AFTER_IDLE = int(os.environ.get("TG_EXIT_AFTER_IDLE", "14400"))  # 4h
IDLE_POLL = int(os.environ.get("TG_IDLE_POLL", "30"))
ONE_SHOT = os.environ.get("TG_ONE_SHOT", "0") == "1"

last_request_id = 0
idle_since = time.time()
request_count = 0
infer_lock = threading.Lock()


def api(method: str, payload: dict, timeout: int = 60) -> dict:
    url = f"{BOT_API}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "description": f"HTTP {exc.code}: {exc.read().decode()[:200]}"}
    except Exception as exc:
        return {"ok": False, "description": str(exc)[:200]}


def send_message(chat_id, text: str, reply_to=None):
    return api("sendMessage", {
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        **({"reply_to_message_id": reply_to} if reply_to else {}),
    })


def send_voice(chat_id, wav_path: str, reply_to=None):
    # Telegram expects normal text fields plus one binary field in multipart/form-data.
    # Keep these separate; treating chat_id as a file tuple causes a runtime unpack error.
    boundary = f"----TG{random.randint(10**8, 10**9)}"
    body = bytearray()

    def add_field(name, value):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    add_field("chat_id", chat_id)
    if reply_to:
        add_field("reply_to_message_id", reply_to)
    with open(wav_path, "rb") as f:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="voice"; filename="voice.wav"\r\n')
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(f.read())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{BOT_API}/sendVoice", data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def speak(text: str, control: str, ref_wav: str):
    """Generate speech via the existing local VoxCPM2 server pipeline (Gradio client)."""
    global model
    from gradio_client import Client, handle_file  # may be missing in CI
    client = Client("http://localhost:7860", verbose=False)
    return client.predict(
        text=text, control=control, audio=handle_file(ref_wav) if ref_wav else None,
        use_prompt_text=False, prompt_text="", cfg_value=2.0, normalize=True,
        denoise=False, inference_timesteps=8, retry_badcase=True, consistency_seed=0,
    )


def generate_via_cli(text: str, control: str, ref_wav: str) -> str:
    """Generate speech with the CLI script (CPU-safe, no server needed)."""
    out = tempfile.mktemp(prefix="thalika-", suffix=".wav")
    env = dict(os.environ)
    env["VOXCPM_DEVICE"] = "cpu"
    env["VOXCPM_LOAD_DENOISER"] = "0"
    import subprocess
    cmd = [
        sys.executable, VOXCPM_SCRIPT,
        "--text", text, "--out", out, "--timesteps", "8", "--cfg", "2.0",
    ]
    if control:
        cmd += ["--control", control]
    if ref_wav:
        cmd += ["--audio", ref_wav]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
    if res.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) < 1024:
        raise RuntimeError(f"generation failed: {res.stdout[-500:]} {res.stderr[-500:]}")
    return out


def handle_voice_request(chat_id, text: str, ref_wav: str, reply_to):
    global request_count
    request_count += 1
    control, script = "", text
    m = re.match(r"^([^|]{2,80})\|(.{1,2000})$", text, re.S)
    if m:
        control, script = m.group(1).strip(), m.group(2).strip()
    if not script:
        send_message(chat_id, "စာသား မပေးဘဲ /voice ပဲ ပို့ထားတဲ့အတွက် ဘာမှ မထုတ်ပေးနိုင်ပါ။\n\nပုံစံ: <code>/voice ကောင်းကောင်းဖတ်ပေးပါ | မငြေးသော နေ့တိုင်းကို သင်ဘဝတစ်ခန်းအဖြစ် ရည်ညွှန်းပါ</code>", reply_to)
        return
    if len(script) > 10000:
        send_message(chat_id, "စာသား 10,000 characters ထက် ကျော်နေပါတယ်။ တိုတိုလေးနဲ့ ထပ်စမ်းပါ။", reply_to)
        return
    send_message(chat_id, f"🎙️ အသံထုတ်နေပါပြီ... ({len(script)} chars, CPU mode ဖြစ်လို့ ၂-၁၀ မိနစ် ကြာနိုင်ပါတယ်)", reply_to)
    start = time.time()
    try:
        with infer_lock:
            wav = generate_via_cli(script, control, ref_wav)
        send_voice(chat_id, wav, reply_to)
        send_message(chat_id, f"✅ ပြီးပါပြီ ({time.time()-start:.0f}s)")
    except Exception as exc:
        send_message(chat_id, f"❌ အသံထုတ်မရပါ: {str(exc)[:200]}")


def poll():
    global last_request_id, idle_since
    params = {"offset": last_request_id + 1, "timeout": 30, "allowed_updates": ["message"]}
    res = api("getUpdates", params, timeout=40)
    if not res.get("ok"):
        print("[tg] getUpdates failed:", res.get("description"), flush=True)
        return
    for upd in res.get("result", []) or []:
        last_request_id = max(last_request_id, upd.get("update_id", 0))
        msg = upd.get("message") or {}
        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()
        if not chat_id or not text.startswith("/voice"):
            continue
        idle_since = time.time()
        ref_wav = ""
        replied = msg.get("reply_to_message") or {}
        audio = replied.get("voice") or replied.get("audio") or replied.get("document")
        if audio and audio.get("file_id"):
            fr = api("getFile", {"file_id": audio["file_id"]})
            if fr.get("ok"):
                path = fr["result"]["file_path"]
                with urllib.request.urlopen(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=120) as r, \
                     tempfile.NamedTemporaryFile(prefix="ref-", suffix=".ogg", delete=False) as f:
                    f.write(r.read())
                    ref_wav = f.name
                # convert to wav for the model
                import subprocess
                wav = ref_wav.rsplit(".", 1)[0] + ".wav"
                subprocess.run(["ffmpeg", "-y", "-i", ref_wav, "-ar", "44100", "-ac", "1", wav],
                               capture_output=True, timeout=120)
                if os.path.isfile(wav):
                    ref_wav = wav
        body = text[len("/voice"):].strip()
        if not body:
            send_message(chat_id, "🎙️ <b>Thalika Voice Bot</b> အသင့်ပါပြီ။\n\nပုံစံ: <code>/voice &lt;စာသား&gt;</code>\nစတိုင်ပါ: <code>/voice &lt;စတိုင်&gt; | &lt;စာသား&gt;</code>\nvoice message တစ်ခုကို reply + /voice လုပ်ရင် အသံ clone လုပ်ပေးပါတယ်", reply_to=msg.get("message_id"))
            continue
        threading.Thread(target=handle_voice_request, args=(chat_id, body, ref_wav, msg.get("message_id")), daemon=True).start()


def main():
    global idle_since
    print("[tg] bot started, polling...", flush=True)
    while True:
        poll()
        if time.time() - idle_since > EXIT_AFTER_IDLE:
            print("[tg] idle timeout, exiting.", flush=True)
            return
        if ONE_SHOT and request_count >= 1:
            print("[tg] one-shot done, exiting.", flush=True)
            return
        time.sleep(IDLE_POLL)


if __name__ == "__main__":
    main()
