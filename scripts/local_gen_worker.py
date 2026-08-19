#!/usr/bin/env python3
"""KM Voice Clone - local CPU voice generation worker.

Job file: /tmp/kmgen_{job_id}.json  -> {"job_id": str, "text": str, "ref_wav": str, "style": str|null}
Output:   /tmp/kmgen_{job_id}.out.json -> {"status": "running"|"done"|"error", "audio": b64|null,
            "sample_rate": int|null, "error": str|null, "progress": 0-100}

Usage: python3 local_gen_worker.py <job_id>
Runs detached; the bot polls the .out.json file for progress.
"""
import base64
import io
import json
import os
import sys
import time
import traceback

import numpy as np

os.environ.setdefault("HF_HOME", "/home/ubuntu/hf_cache")
os.environ.setdefault("HF_HUB_CACHE", "/home/ubuntu/hf_cache")

JOB_DIR = "/tmp"

MODEL = None


def write_out(job_id, status, audio=None, sample_rate=None, error=None, progress=0):
    d = {"status": status, "audio": audio, "sample_rate": sample_rate,
         "error": (str(error)[:1200] if error else None), "progress": progress}
    with open(os.path.join(JOB_DIR, f"kmgen_{job_id}.out.json"), "w") as f:
        json.dump(d, f)


def load_model():
    global MODEL
    if MODEL is not None:
        return MODEL
    import torch  # noqa
    from voxcpm import VoxCPM  # noqa
    print("[km-worker] downloading/loading VoxCPM2 (first run ~10-20 min)...", flush=True)
    MODEL = VoxCPM.from_pretrained("openbmb/VoxCPM2", device="cpu")
    print("[km-worker] warming up...", flush=True)
    try:
        MODEL.generate(text="This is a warm-up test sentence.",
                       cfg_value=2.0, inference_timesteps=8)
    except Exception as e:
        print(f"[km-worker] warmup non-fatal: {e}", flush=True)
    print("[km-worker] model ready", flush=True)
    return MODEL


def decode_ref(raw_path):
    """Decode reference audio from any common format (wav/ogg/mp3/m4a/opus)."""
    import soundfile as sf
    try:
        wav, sr = sf.read(raw_path)
        return wav, int(sr)
    except Exception as e1:
        pass
    try:
        import torchaudio
        t, tsr = torchaudio.load(raw_path)
        wav = t.to("cpu").float().mean(dim=0).numpy()
        return wav.astype("float32"), int(tsr)
    except Exception as e2:
        raise RuntimeError(f"cannot decode reference audio (sf: {e1}; torchaudio: {e2})")


def run_job(job_id):
    job_path = os.path.join(JOB_DIR, f"kmgen_{job_id}.json")
    with open(job_path) as f:
        job = json.load(f)
    text = job.get("text", "").strip()
    ref_wav = job.get("ref_wav")
    if not text:
        write_out(job_id, "error", error="text required")
        return
    if not ref_wav or not os.path.exists(ref_wav):
        write_out(job_id, "error", error="reference audio missing")
        return

    model = load_model()
    write_out(job_id, "running", progress=5)
    # estimate audio token budget from text token count so the model does not
    # stop before finishing the full sentence
    try:
        text_tokens = model.tts_model.text_tokenizer(text)
        min_len = min(len(text_tokens) + 8, 4096)
    except Exception:
        min_len = 16

    wav, sr = decode_ref(ref_wav)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    ref = ref_wav  # already a normalized wav
    wav = model.generate(text=text, reference_wav_path=ref,
                         cfg_value=2.0, inference_timesteps=32,
                         min_len=min_len, max_len=4096,
                         retry_badcase=False, normalize=True)
    try:
        out_sr = int(model.tts_model.sample_rate)
    except Exception:
        out_sr = 48000
    # generate() returns a numpy array (float32) on CPU
    wav = np.asarray(wav, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    try:
        wav = _trim_silence_edges(wav, out_sr)
    except Exception:
        pass
    buf = io.BytesIO()
    _sf_write(buf, wav, out_sr)
    b64 = base64.b64encode(buf.getvalue()).decode()
    write_out(job_id, "done", audio=b64, sample_rate=out_sr, progress=100)


def _t_np_asarray(wav):
    import numpy as np
    a = np.asarray(wav, dtype="float32").ravel()
    return a


def _trim_silence_edges(wav, sr, top_db=35.0, keep_ms=80):
    """Trim leading/trailing silence, keeping a short tail of the last sound."""
    import numpy as np
    try:
        from librosa import effects  # noqa
    except Exception:
        return wav
    a = np.asarray(wav, dtype="float32")
    t = effects.trim(a, top_db=top_db, frame_length=2048, hop_length=512)[0]
    if len(t) < sr:
        return t
    keep = int(keep_ms * sr / 1000)
    if len(t) > keep:
        return t
    return t


def _sf_write(buf, wav, sr):
    import soundfile as sf
    sf.write(buf, wav, sr, subtype="PCM_16", format="WAV")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: local_gen_worker.py <job_id>")
        sys.exit(1)
    job_id = sys.argv[1]
    try:
        run_job(job_id)
    except Exception as e:
        write_out(job_id, "error", error=f"{e}\n{traceback.format_exc()[-800:]}")
    print("[km-worker] finished", flush=True)
