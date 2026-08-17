"""
Thalika one-shot VoxCPM2 generation for GitHub Actions (CPU-mode, no Gradio server).

Loads VoxCPM2 once, generates a requested script (optionally cloned from a reference
audio file uploaded via the Telegram bot), and writes a 48kHz mono 24-bit PCM WAV.

Usage (from repo root, with VOXCPM venv active):
  python scripts/voxcpm-generate.py \
      --text "မငြေးသော နေ့တစ်နေ့တိုင်းကို သင်ဘဝတစ်ခန်းအဖြစ် ရည်ညွှန်းပါ" \
      [--control "ယောက်ျားလေးအသံ နှေးနှေး"] \
      [--audio /path/to/reference.wav] \
      --out /tmp/output.wav \
      [--timesteps 10] [--cfg 2.0] [--seed 0]
"""
import argparse
import os
import random
import sys

import numpy as np
import torch

# Make `voxcpm` importable from local-server's virtualenv if it was not sourced.
SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "local-server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

try:
    from voxcpm import VoxCPM  # noqa: E402
except ImportError:
    import site  # noqa: E402

    def _load_venv():
        import site  # noqa: F811

        venv_site = os.path.join(SERVER_DIR, ".voxcpm-venv", "lib")
        if os.path.isdir(venv_site):
            # lib/{site-packages,pythonX.Y/site-packages}
            for root, _dirs, files in os.walk(venv_site):
                if root.endswith("site-packages"):
                    site.addsitedir(root)
            import voxcpm  # noqa: F811

    _load_venv()
    from voxcpm import VoxCPM  # noqa: E402,F811

import soundfile as sf  # noqa: E402


def seed_everything(seed: int) -> int:
    stable = max(0, int(seed or 0)) % (2**31)
    random.seed(stable)
    np.random.seed(stable)
    torch.manual_seed(stable)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(stable)
    return stable


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="Script text to speak (Burmese supported)")
    ap.add_argument("--control", default="", help="(style/description) prefix -> controllable cloning")
    ap.add_argument("--audio", default=None, help="Reference wav for cloning")
    ap.add_argument("--out", required=True, help="Output wav path")
    ap.add_argument("--timesteps", type=int, default=4, help="4-50 (CPU: keep small for fast replies)")
    ap.add_argument("--cfg", type=float, default=2.0, help="cfg_value 1.0-4.0")
    ap.add_argument("--seed", type=int, default=0, help="Consistency seed")
    ap.add_argument("--steps-threshold", type=int, default=10000, help="Split text above this many chars")
    args = ap.parse_args()

    text = args.text.strip()
    if not text:
        print("[thalika-cli] ERROR: empty text", file=sys.stderr)
        return 1

    if args.control and args.control.strip():
        text = f"({args.control.strip()}) {text}"

    device = os.environ.get("VOXCPM_DEVICE", "auto").strip().lower() or "cpu"
    model_dir = os.environ.get("VOXCPM_MODEL_DIR", "openbmb/VoxCPM2")

    print("[thalika-cli] loading VoxCPM2 (this takes a while on first run)...", flush=True)
    model = VoxCPM.from_pretrained(model_dir, device=device)
    print("[thalika-cli] warmup ...", flush=True)
    try:
        model.generate(text="warm up", cfg_value=2.0, inference_timesteps=4)
    except Exception as exc:  # warmup is best-effort
        print(f"[thalika-cli] warmup skipped: {exc}", file=sys.stderr, flush=True)
    print("[thalika-cli] ready.", flush=True)

    kwargs = {
        "text": text,
        "cfg_value": float(args.cfg),
        "inference_timesteps": min(50, max(4, int(args.timesteps))),
        "retry_badcase": True,
        "normalize": True,
        "denoise": bool(os.environ.get("VOXCPM_LOAD_DENOISER", "0") not in ("0", "false")),
    }
    if args.audio:
        kwargs["reference_wav_path"] = args.audio

    stable = seed_everything(args.seed)
    print(f"[thalika-cli] seed={stable} cfg={args.cfg:.2f} steps={kwargs['inference_timesteps']}", flush=True)
    wav = model.generate(**kwargs)
    wav = np.asarray(wav, dtype=np.float32)
    sr = int(getattr(model, "tts_model", None) and model.tts_model.sample_rate or 44100)
    sr = 48000
    sf.write(args.out, wav, sr, subtype="PCM_16")
    os.sync()
    print(f"[thalika-cli] wrote {args.out} ({len(wav)/sr:.1f}s @ {sr}Hz mono PCM16)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
