export const MAX_SCRIPT_CHARACTERS = 50000;

// Two opposing failure modes (both maintainer-confirmed, VoxCPM #302):
//   bigger chunks -> long single takes drift mid-take (conditioning goes self-referential);
//   smaller chunks -> more independent takes -> more segment-to-segment timbre variation.
// 180 (~8-12s) is a middle guess; the real sweet spot is per-voice and only your ears can pick it.
// Tune with VOXCPM_CHUNK_CHARS in .env.local (no rebuild). ponytail: calibration knob.
const DEFAULT_REMOTE_TTS_CHUNK_CHARACTERS = 180;
const MIN_REMOTE_TTS_CHUNK_CHARACTERS = 80;
const MAX_REMOTE_TTS_CHUNK_CHARACTERS = 400;

function resolveChunkCharacters() {
  const raw = Number(process.env.VOXCPM_CHUNK_CHARS);
  if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_REMOTE_TTS_CHUNK_CHARACTERS;
  // Very large chunks drift; very small chunks increase segment-to-segment variation.
  return Math.round(Math.min(MAX_REMOTE_TTS_CHUNK_CHARACTERS, Math.max(MIN_REMOTE_TTS_CHUNK_CHARACTERS, raw)));
}

export const REMOTE_TTS_CHUNK_CHARACTERS = resolveChunkCharacters();
