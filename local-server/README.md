# Thalika Local VoxCPM2 Server

This is the production inference backend for Thalika. It runs VoxCPM2 on your
own machine as a **separate process** and exposes the same Gradio `/generate`
endpoint the Next.js app already speaks — so once it's up, you just point the app
at `http://localhost:7860` (or click **Start** in the app's Voice Settings).

Local inference keeps model execution on the device, avoids shared Space queues, and
lets Thalika control sampling, serialization, chunk consistency, and quality tuning.

## Requirements

- **Python 3.10, 3.11, or 3.12** — Python 3.13+ is **not** supported (the `voxcpm` /
  PyTorch stack does not build on it yet). Check: `python3 --version`.
- Ideally a GPU: **Apple Silicon (MPS)** works and is much faster than CPU; **CUDA**
  on NVIDIA is fastest. CPU works but is slow.
- ~5 GB free disk for the model (downloaded once, then cached).
- 16 GB RAM recommended. CPU-only operation works but is substantially slower.

## Quick start

The easiest way is the launcher script from the repo root:

```bash
bash scripts/voxcpm-local.sh
```

It creates a virtualenv (`.voxcpm-venv/`), installs `requirements.txt`, and runs
`server.py`. The first run downloads the ~2B model, so be patient (several minutes).

When you see `Running on local URL: http://0.0.0.0:7860`, the server is ready.

## Manual install (if you prefer control over the Python version)

### Option A — uv (recommended; fetches an isolated Python 3.11)

```bash
# install uv once:  brew install uv   (macOS)  or see https://docs.astral.sh/uv/
cd local-server
uv venv --python 3.11
source .voxcpm-venv/bin/activate
uv pip install -r requirements.txt
python server.py
```

### Option B — pyenv / system Python 3.10–3.12

```bash
cd local-server
python3.11 -m venv .voxcpm-venv          # use 3.10 / 3.11 / 3.12
source .voxcpm-venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python server.py
```

## Connecting Thalika to the local server

With the server running on `:7860`, either click **Start local model** in
**Voice Over → Voice Settings**, or set the endpoint in `.env.local`:

   ```bash
   HF_VOXCPM2_URL=http://localhost:7860
   ```

Restart the app after changing `.env.local`.

## Configuration (environment variables)

| Variable | Default | Effect |
| --- | --- | --- |
| `VOXCPM_DEVICE` | `auto` | `auto` / `cuda` / `mps` / `cpu` |
| `VOXCPM_TIMESTEPS` | `10` | Diffusion sampling steps. Higher = better quality, slower. Try `20`–`30`. |
| `VOXCPM_PORT` | `7860` | Port the Gradio server listens on (must match the app's endpoint). |

Example for higher quality on Apple Silicon:

```bash
VOXCPM_DEVICE=auto VOXCPM_TIMESTEPS=24 python server.py
```

## How it integrates with the app

The app does **not** embed Python. It launches this server as a background process
via `/api/voxcpm-local` and calls it over localhost HTTP. The `generate()` signature
mirrors the app's 11-argument contract, including inference steps, bad-case retry,
and a consistency seed.

The model server serializes requests with a single inference lock and resets Python,
NumPy, and PyTorch random state before each chunk. Thalika derives one stable seed
from the voice reference and settings, reuses it for every chunk, rejects pace or
loudness outliers, and applies conservative PCM loudness matching before merge.

Key files:
- `local-server/server.py` — this server
- `scripts/voxcpm-local.sh` — one-command launcher
- `src/app/api/voxcpm-local/route.ts` — app-side start/stop/status
- `src/lib/providers/voxcpm2-provider.ts` — the client that calls `/generate`

## Troubleshooting

- **`ModuleNotFoundError: voxcpm`** — you're on the wrong Python. This needs 3.10–3.12.
  Use `uv` (Option A) to get an isolated 3.11.
- **First run is slow** — it's downloading the model. Subsequent runs use the cache.
- **`MPS` errors on older macOS** — set `VOXCPM_DEVICE=cpu` as a fallback.
- **App health badge stays red** — confirm the server is up:
  `curl -s http://localhost:7860/gradio_api/info | head`, and that `HF_VOXCPM2_URL`
  (or the in-app endpoint) is `http://localhost:7860`.
