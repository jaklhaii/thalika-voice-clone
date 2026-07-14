export const MAX_SCRIPT_CHARACTERS = 50000;

// Two opposing failure modes (both maintainer-confirmed, VoxCPM #302):
//   bigger chunks -> long single takes drift mid-take (conditioning goes self-referential);
//   smaller chunks -> more independent takes -> more segment-to-segment timbre variation.
// 180 (~8-12s) is a middle guess; the real sweet spot is per-voice and only your ears can pick it.
// Tune with VOXCPM_CHUNK_CHARS in .env.local (no rebuild). ponytail: calibration knob.
export const REMOTE_TTS_CHUNK_CHARACTERS = Number(process.env.VOXCPM_CHUNK_CHARS) || 180;
