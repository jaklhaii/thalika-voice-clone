# KM Voice Clone - Colab GPU Server (FastAPI + Cloudflare Quick Tunnel)
# Run inside Colab (foreground cell). Outputs PUBLIC_URL when ready.
import base64
import io
import os
import re
import subprocess
import sys
import tempfile
import time

DEVICE = "cuda"

print("[km] installing dependencies...", flush=True)
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "torch", "torchaudio", "transformers", "soundfile",
     "fastapi", "uvicorn", "pydantic", "voxcpm"],
    check=True,
)
_install_check = subprocess.run([sys.executable, "-m", "pip", "show", "voxcpm"], capture_output=True, text=True)
print("[km] voxcpm installed:", bool(_install_check.stdout), flush=True)
print("[km] installing cloudflared...", flush=True)
subprocess.run([
    "wget", "-q", "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
    "-O", "/usr/local/bin/cloudflared",
], check=False)
subprocess.run(["chmod", "+x", "/usr/local/bin/cloudflared"], check=False)

os.environ["HF_HOME"] = "/content/hf_cache"
print("[km] downloading VoxCPM2 model (~8GB, may take 5-8 min)...", flush=True)

import soundfile as sf          # noqa: E402
import torch                    # noqa: E402
from fastapi import FastAPI     # noqa: E402
from pydantic import BaseModel  # noqa: E402

from voxcpm import VoxCPM   # noqa: E402

print(f"[km] device={DEVICE}", flush=True)
model = VoxCPM.from_pretrained("openbmb/VoxCPM2")

print("[km] warming up model...", flush=True)
model.generate(
    text="This is a warm-up test sentence.",
    cfg_value=2.0,
    inference_timesteps=8,
)
print("[km] model ready", flush=True)

# ---------- FastAPI ----------
app = FastAPI(title="KM Voice Clone")


class GenRequest(BaseModel):
    text: str
    style: str | None = None
    audio: str | None = None  # base64 reference audio


@app.post("/generate")
def generate(req: GenRequest):
    if not req.audio:
        return {"error": "reference audio required"}
    if not (req.text or "").strip():
        return {"error": "text required"}

    raw = base64.b64decode(req.audio)
    tmp = tempfile.NamedTemporaryFile(suffix=".ref", delete=False)
    tmp.write(raw)
    tmp.close()

    try:
        return _do_generate(req, tmp.name)
    except Exception as e:
        import traceback as _tb
        _tb.print_exc(flush=True)
        return {"error": "generation failed: " + str(e)}


def _do_generate(req, raw_path):
    try:
        wav, sr = sf.read(raw_path)
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        ref = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(ref.name, wav.astype("float32"), sr)
        ref.close()

        # High quality: 32 timesteps, strong guidance
        # Correct VoxCPM2 API: reference_wav_path (NOT "audio")
        wav = model.generate(
            text=req.text,
            reference_wav_path=ref.name,
            cfg_value=2.0,
            inference_timesteps=32,
        )
        # wav is a numpy.ndarray (float32, CPU)
        if isinstance(wav, tuple):
            wav, sr = wav
        elif isinstance(wav, str):
            wav, sr = sf.read(wav)
        if isinstance(wav, np.ndarray) and wav.dtype == "float32" and wav.max() <= 1.001:
            pass  # fine
        wav = np.asarray(wav, dtype="float32").ravel()
        out_sr = 48000
        try:
            out_sr = getattr(model, "tts_model", None) and model.tts_model.sample_rate or 48000
        except Exception:
            out_sr = 48000
        wav = np.asarray(wav, dtype="float32")
        out_buf = io.BytesIO()
        sf.write(out_buf, wav, out_sr, subtype="PCM_16", format="WAV")
        return {"audio": base64.b64encode(out_buf.getvalue()).decode(), "sample_rate": out_sr}
    finally:
        os.unlink(raw_path)
        if os.path.exists(ref.name):
            os.unlink(ref.name)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Start Cloudflare tunnel first, then run uvicorn directly ----------
print("[km] starting Cloudflare quick tunnel...", flush=True)
t = subprocess.Popen(
    ["cloudflared", "tunnel", "--url", "http://localhost:8000"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
public_url = None
start = time.time()
while time.time() - start < 120:
    line = t.stdout.readline()
    if not line:
        break
    m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
    if m:
        public_url = m.group(0)
        break
    print("[km] tunnel:", line.strip(), flush=True)

if public_url:
    print(f"PUBLIC_URL={public_url}", flush=True)
    print("[km] KEEP THIS CELL RUNNING — server is live", flush=True)
else:
    print("[km] ERROR: could not get public URL", flush=True)

import threading  # noqa: E402
import asyncio  # noqa: E402
import uvicorn  # noqa: E402

def _run_server():
    asyncio.set_event_loop(asyncio.new_event_loop())
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

print("[km] starting uvicorn in thread...", flush=True)
th = threading.Thread(target=_run_server, daemon=True)
th.start()
time.sleep(3)

# sanity check: uvicorn must be listening
for _ in range(20):
    try:
        urllib.request.urlopen("http://localhost:8000/health")
        print("[km] uvicorn listening on :8000", flush=True)
        break
    except Exception:
        time.sleep(1)
else:
    print("[km] ERROR: uvicorn failed to start", flush=True)

# keep cell alive forever (server must stay running)
while True:
    time.sleep(60)
