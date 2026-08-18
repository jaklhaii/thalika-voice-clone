#!/usr/bin/env python3
"""
KM Voice Clone — GitHub Actions queue worker (CPU-only, no persistent server).
===============================================================================
Runs inside the scheduled GitHub Action AFTER bot.py processes Telegram messages.

Flow:
  1. Scan scripts/ghq/pending/*.json  (each: {job_id, user_id, chat_id,
     start_msg_id, text, voice_name, ts})
  2. For each job: load GGUF VoxCPM2 (CPU), generate 48kHz WAV using the user's
     reference voice (scripts/ghq/refs/{user_id}_{voice_name}.wav)
  3. Write result to scripts/ghq/done/{job_id}.json {job_id, wav_b64, done_at}
     and delete the pending file

Memory: GGUF Q8_0 BaseLM (1.6GB) + Acoustic F16 (1.7GB) ≈ 3.3GB total.
        Runner provides 7GB RAM + we add 4GB swap. Fits comfortably.

Speed: ~2 vCPU → RTF roughly 5-10x for short clips; a 10s clip takes a few minutes.

Env:
  VOXCPM_MODEL_DIR   (default DennisHuang648/VoxCPM2-GGUF)
  HF_TOKEN           (optional — speeds up gated download, not needed here)
"""
import base64
import glob
import os
import sys
import time

JOB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "ghq")
PENDING = os.path.join(JOB_DIR, "pending")
DONE = os.path.join(JOB_DIR, "done")
REFS = os.path.join(JOB_DIR, "refs")

os.makedirs(PENDING, exist_ok=True)
os.makedirs(DONE, exist_ok=True)
os.makedirs(REFS, exist_ok=True)

TSTEPS = 16        # quality/speed tradeoff (higher = better, slower)
CFG = 2.0


def load_model():
    """Bootstrap the voxcpm package in a venv if needed, then load GGUF model."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        from voxcpm import VoxCPM  # noqa: E402
    except ImportError:
        # fallback: scan for a venv created by a launcher
        import site as _site

        def _try(root):
            for r, _d, _f in _site.os.walk(root):
                if r.endswith("site-packages"):
                    _site.addsitedir(r)

        for cand in (
            os.path.join(repo_root, "scripts", ".voxcpm-venv", "lib"),
            os.path.join(repo_root, "local-server", ".voxcpm-venv", "lib"),
        ):
            if os.path.isdir(cand):
                _try(cand)
        from voxcpm import VoxCPM  # noqa: E402, F811

    model_dir = os.environ.get("VOXCPM_MODEL_DIR", "DennisHuang648/VoxCPM2-GGUF")
    print(f"[gh-worker] loading {model_dir} (cpu, may take 5-10 min first time)...", flush=True)
    t0 = time.time()
    model = VoxCPM.from_pretrained(model_dir, device="cpu")
    print(f"[gh-worker] model loaded in {time.time() - t0:.0f}s", flush=True)
    print("[gh-worker] warming up...", flush=True)
    try:
        model.generate(text="warm up", cfg_value=CFG, inference_timesteps=4)
        print("[gh-worker] warmup ok", flush=True)
    except Exception as e:  # best-effort
        print(f"[gh-worker] warmup skipped: {e}", flush=True)
    return model


def run_job(model, job_path: str) -> None:
    import json

    import numpy as np
    import soundfile as sf

    with open(job_path) as f:
        job = json.load(f)
    job_id = job["job_id"]
    text = job["text"].strip()
    user_id = job["user_id"]
    voice_name = job["voice_name"].strip().lower()
    ref_path = os.path.join(REFS, f"{user_id}_{voice_name}.wav")
    if not os.path.isfile(ref_path):
        _mark_failed(job_id, "reference audio missing in repo (ref wav deleted?)")
        os.remove(job_path)
        return

    print(f"[gh-worker] job {job_id}: generating for user {user_id} voice={voice_name}...", flush=True)
    t0 = time.time()
    kwargs = {
        "text": text,
        "prompt_wav_path": ref_path,
        "cfg_value": CFG,
        "inference_timesteps": TSTEPS,
        "retry_badcase": False,   # keep predictable duration in CI
        "normalize": True,
        "denoise": False,
    }
    wav = model.generate(**kwargs)
    wav = np.asarray(wav, dtype=np.float32)
    sr = 48000
    tmp_out = os.path.join(DONE, f"{job_id}.wav")
    sf.write(tmp_out, wav, sr, subtype="PCM_16")
    b64 = base64.b64encode(open(tmp_out, "rb").read()).decode()
    os.remove(tmp_out)

    done = {
        "job_id": job_id,
        "wav_b64": b64,
        "sample_rate": sr,
        "duration_s": round(len(wav) / sr, 2),
        "done_at": int(time.time()),
    }
    with open(os.path.join(DONE, f"{job_id}.json"), "w") as f:
        json.dump(done, f)
    os.remove(job_path)
    print(f"[gh-worker] job {job_id} done in {time.time() - t0:.0f}s -> {len(b64)//1024}KB b64", flush=True)


def _mark_failed(job_id: str, reason: str) -> None:
    import json

    with open(os.path.join(DONE, f"{job_id}.json"), "w") as f:
        json.dump({"job_id": job_id, "error": reason, "done_at": int(time.time())}, f)


def main() -> int:
    pending = sorted(glob.glob(os.path.join(PENDING, "*.json")))
    if not pending:
        print("[gh-worker] no pending jobs", flush=True)
        return 0
    print(f"[gh-worker] {len(pending)} pending job(s)", flush=True)

    # install soundfile if absent
    try:
        import soundfile  # noqa: F401
    except ImportError:
        os.system(f"{sys.executable} -m pip install -q soundfile")
        import soundfile  # noqa: F401,F811

    model = load_model()
    for p in pending:
        try:
            run_job(model, p)
        except Exception as e:
            import traceback as _tb

            _tb.print_exc()
            job_id = os.path.basename(p)[:-5]
            print(f"[gh-worker] job {job_id} FAILED: {e}", flush=True)
            _mark_failed(job_id, f"generation error: {e}")
            try:
                os.remove(p)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback as _tb

        _tb.print_exc()
        print(f"[gh-worker] FATAL: {e}", flush=True)
        sys.exit(1)
