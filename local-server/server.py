"""
Thalika local VoxCPM2 inference server.

This is a SEPARATE process from the Next.js app. The app talks to it over HTTP through
the managed local Gradio /generate endpoint at http://localhost:7860.

INVARIANT: the first 8 generate() arguments match the public Space contract. The local
server adds inference_timesteps, retry_badcase, and consistency_seed in that order
(src/lib/providers/voxcpm2-provider.ts):
    [text, control, audio, use_prompt_text, prompt_text, cfg_value, normalize, denoise,
     inference_timesteps, retry_badcase, consistency_seed]
The api_name MUST be "generate" so the app's POST /gradio_api/call/generate works.

Requirements: Python 3.10-3.12 (3.13+ is not supported by the voxcpm/torch stack).
The ~2B model is downloaded on first run and cached locally.
"""

import os
import random
import sys
import tempfile
import threading

import gradio as gr
import numpy as np
import soundfile as sf
import torch

from voxcpm import VoxCPM

# ponytail: torch auto-picks the device (CUDA if present, else CPU; MPS support depends on the
# voxcpm build). Add a device knob here only if CPU is too slow and MPS isn't auto-selected.
# VOXCPM_MODEL_DIR points at a pre-downloaded local copy (e.g. from ModelScope); else pull from HF.
MODEL = os.environ.get("VOXCPM_MODEL_DIR", "openbmb/VoxCPM2")
DEVICE = os.environ.get("VOXCPM_DEVICE", "auto").strip().lower()
if DEVICE not in {"auto", "cpu", "mps", "cuda"}:
    raise ValueError("VOXCPM_DEVICE must be auto, cpu, mps, or cuda.")
# Denoiser is OFF by default: it adds ~30s startup and the zipenhancer errors on some builds
# (e.g. Apple MPS). Opt in with VOXCPM_LOAD_DENOISER=1 on hardware where it works; the per-request
# `denoise` toggle is a safe no-op while it's off.
LOAD_DENOISER = os.environ.get("VOXCPM_LOAD_DENOISER", "0") not in ("0", "false", "no")
print(
    f"[thalika-local] loading VoxCPM2 from '{MODEL}' "
    f"(device={DEVICE}, denoiser={LOAD_DENOISER}) ...",
    flush=True,
)
try:
    model = VoxCPM.from_pretrained(
        MODEL,
        load_denoiser=LOAD_DENOISER,
        device=None if DEVICE == "auto" else DEVICE,
    )
    print(f"[thalika-local] model loaded on {model.tts_model.device}.", flush=True)
except Exception as exc:  # noqa: BLE001 - surface a clear startup failure
    print(f"[thalika-local] FATAL: could not load VoxCPM2: {exc}", file=sys.stderr, flush=True)
    raise

# Warm the generate path BEFORE serving so the first real request isn't a cold take (MPS lazy
# init / first-pass artifacts the user hears as noise on chunk 1). Output discarded.
try:
    print("[thalika-local] warmup ...", flush=True)
    model.generate(text="warm up", cfg_value=2.0, inference_timesteps=4)
    print("[thalika-local] warmup done.", flush=True)
except Exception as exc:  # noqa: BLE001 - warmup is best-effort
    print(f"[thalika-local] warmup skipped: {exc}", file=sys.stderr, flush=True)


# VoxCPM and the process-wide RNG are shared state. Serializing local inference prevents two
# browser jobs from changing the seed or overwriting an output while another take is running.
INFERENCE_LOCK = threading.Lock()


def seed_inference(seed):
    """Reset every RNG used by VoxCPM before a take for reproducible chunk identity."""
    stable_seed = max(0, int(seed or 0)) % (2**31)
    random.seed(stable_seed)
    np.random.seed(stable_seed)
    torch.manual_seed(stable_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(stable_seed)
    return stable_seed


def generate(
    text,
    control,
    audio,
    use_prompt_text,
    prompt_text,
    cfg_value,
    normalize,
    denoise,
    inference_timesteps=None,
    retry_badcase=None,
    consistency_seed=None,
):
    """Exposes the full VoxCPM2 surface via the app's base payload and local controls:
      args 1-8 (app's public-Space signature):
        text, control, audio, use_prompt_text, prompt_text, cfg_value, normalize, denoise
      args 9-11 (local server only — the public Space's 8-arg signature would reject them):
        inference_timesteps : diffusion sampling steps (the biggest quality/stability lever)
        retry_badcase       : auto-retry degenerate takes (repeat/echo) on the server side
        consistency_seed    : same seed for every first take in one voice job
      - control non-empty -> "(style/description) text" prefix = Controllable Cloning / Voice Design
      - audio present      -> Controllable Cloning (timbre from the reference)
      - audio absent       -> Voice Design (a brand-new voice from the description, no reference)
      - use_prompt_text + prompt_text -> Ultimate Cloning (exact-transcript continuation)
      - Context-Aware prosody is automatic. (Streaming intentionally not wired — file-based pipeline.)
    """
    if not text or not text.strip():
        raise gr.Error("Text is required.")

    # The model steers style/voice via a "(...)" prefix on the text — that's how control works.
    if control and control.strip():
        text = f"({control.strip()}) {text}"

    # Reference is OPTIONAL: with it -> cloning; without it -> Voice Design.
    ref_path = None
    if audio is not None:
        ref_path = audio if isinstance(audio, str) else None
        if ref_path is None:
            try:
                sample_rate, samples = audio  # (int, ndarray)
            except (TypeError, ValueError) as exc:
                raise gr.Error("Reference audio could not be read.") from exc
            ref_path = os.path.join(tempfile.gettempdir(), "thalika_reference.wav")
            sf.write(ref_path, np.asarray(samples), int(sample_rate))

    cfg = float(cfg_value) if cfg_value is not None else 2.0
    timesteps = int(inference_timesteps) if inference_timesteps else int(os.environ.get("VOXCPM_TIMESTEPS", "10"))
    # retry_badcase: True = auto-retry degenerate (repeat/echo) takes. Defaults True in the model;
    # the app always sends True for local. None (e.g. an older caller) -> keep the model default.
    do_retry = bool(retry_badcase) if retry_badcase is not None else True

    # normalize (text) + denoise (reference) are forwarded; denoise is gated on the denoiser load.
    kwargs = {
        "text": text,
        "cfg_value": cfg,
        "inference_timesteps": timesteps,
        "retry_badcase": do_retry,
        "normalize": bool(normalize),
        "denoise": bool(denoise) and LOAD_DENOISER,
    }
    # Tunable stability knob: lower ratio = retry more aggressively on degenerate takes (default 6.0).
    ratio = os.environ.get("VOXCPM_RETRY_RATIO")
    if ratio:
        kwargs["retry_badcase_ratio_threshold"] = float(ratio)
    if ref_path:
        kwargs["reference_wav_path"] = ref_path
        if use_prompt_text and prompt_text and prompt_text.strip():
            kwargs["prompt_wav_path"] = ref_path
            kwargs["prompt_text"] = prompt_text.strip()
    with INFERENCE_LOCK:
        stable_seed = seed_inference(consistency_seed)
        print(
            f"[thalika-local] generate seed={stable_seed} cfg={cfg:.2f} steps={timesteps}",
            flush=True,
        )
        wav = model.generate(**kwargs)

    # A unique file avoids cross-job collisions in Gradio's output cache. The Next.js pipeline
    # immediately downloads and converts it to the 48kHz mono 24-bit PCM master format.
    output = tempfile.NamedTemporaryFile(prefix="thalika-output-", suffix=".wav", delete=False)
    out_path = output.name
    output.close()
    sf.write(out_path, np.asarray(wav, dtype=np.float32), model.tts_model.sample_rate, subtype="PCM_16")
    return out_path


demo = gr.Interface(
    fn=generate,
    inputs=[
        gr.Textbox(label="text"),
        gr.Textbox(label="control"),
        gr.Audio(label="audio", type="filepath"),
        gr.Checkbox(label="use_prompt_text", value=False),
        gr.Textbox(label="prompt_text", value=""),
        gr.Slider(1.0, 4.0, value=2.0, step=0.1, label="cfg_value"),
        gr.Checkbox(label="normalize", value=True),
        gr.Checkbox(label="denoise", value=False),
        gr.Slider(4, 50, value=10, step=1, label="inference_timesteps"),
        gr.Checkbox(label="retry_badcase", value=True),
        gr.Number(value=0, precision=0, label="consistency_seed"),
    ],
    outputs=gr.Audio(label="output"),
    api_name="generate",
    flagging_mode="never",  # Gradio 6 renamed allow_flagging -> flagging_mode
    concurrency_limit=1,
    time_limit=None,
    delete_cache=(3600, 3600),
)
demo.queue(default_concurrency_limit=1, max_size=8)

if __name__ == "__main__":
    port = int(os.environ.get("VOXCPM_PORT", "7860"))
    demo.launch(server_name="0.0.0.0", server_port=port)
