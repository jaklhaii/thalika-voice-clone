# KM Voice Clone - Colab GPU Server (FastAPI + ngrok)
# Run inside Colab terminal with:
#   python3 colab-server.py
# Outputs PUBLIC_URL=<ngrok url> when ready. Keep the cell/terminal running.
import base64
import io
import os
import subprocess
import sys
import tempfile
import time

# ---------- 1. dependencies ----------
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "torch", "torchaudio", "transformers", "soundfile",
     "fastapi", "uvicorn", "ngrok"],
    check=False,
)

import soundfile as sf          # noqa: E402
import torch                    # noqa: E402
from fastapi import FastAPI     # noqa: E402
from pydantic import BaseModel  # noqa: E402

print("[km] installing ok, downloading VoxCPM2 (~8GB)...", flush=True)

from voxcpm.cpm import VoxCPM   # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[km] device={DEVICE}", flush=True)

MODEL_DIR = os.environ.get("VOXCPM_MODEL_DIR")
if MODEL_DIR and os.path.isdir(MODEL_DIR):
    model = VoxCPM.from_pretrained(MODEL_DIR)
else:
    model = VoxCPM.from_pretrained("openbmb/VoxCPM2")

print("[km] warm-up...", flush=True)
model.generate(
    "Hello, this is a quick warm-up test.",
    audio=None,
    temperature=0.9,
    cfg_value=2.0,
    inference_timesteps=8,
    retry_badcase=True,
    consistency_seed=0,
    output_path="warmup.wav",
)
print("[km] model ready", flush=True)

# ---------- 2. FastAPI ----------
app = FastAPI(title="KM Voice Clone")


class GenRequest(BaseModel):
    text: str
    style: str | None = None
    audio: str | None = None  # base64 WAV/OGG/M4A reference audio


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
        wav, sr = sf.read(tmp.name)
        # VoxCPM works best with mono 16kHz-ish WAV
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        ref = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        sf.write(ref.name, wav, sr)
        ref.close()

        wav = model.generate(
            req.text,
            control=req.style or None,
            audio=ref.name,
            temperature=0.9,
            cfg_value=2.0,
            inference_timesteps=32,
            retry_badcase=True,
            consistency_seed=0,
            output_path="out.wav",
        )
        if not wav:
            wav, sr = sf.read("out.wav")
        out_buf = io.BytesIO()
        sf.write(out_buf, wav, 48000, subtype="PCM_16", format="WAV")
        return {"audio": base64.b64encode(out_buf.getvalue()).decode(), "sample_rate": 48000}
    finally:
        os.unlink(tmp.name)
        if os.path.exists(ref.name):
            os.unlink(ref.name)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- 3. start server + ngrok ----------
print("[km] starting uvicorn + ngrok...", flush=True)
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "__main__:app", "--host", "0.0.0.0", "--port", "8000"],
)

import ngrok  # noqa: E402

listener = ngrok.connect("8000")
public_url = listener.url()
print(f"PUBLIC_URL={public_url}", flush=True)
while True:
    time.sleep(10)
