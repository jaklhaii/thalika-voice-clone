"use client";

// A reusable status dot — the "motion-as-teaching" primitive. One glance tells you the state
// (steady = settled, pulsing = in-flight, faint = idle) without reading text. Used by the VoxCPM
// health badge and the local-server line. The exact text label always travels alongside it for
// screen readers + precise reading (mirrors Phase 1's captioned chunk cells).
//
// Tone is intentionally small so both call sites share one vocabulary:
//   - success  : steady green — connected / running
//   - warning  : amber pulse  — transient (rate-limited / timeout / starting… / loading)
//   - danger   : steady red   — unavailable / invalid_response
//   - idle     : faint gray   — not checked / stopped
// `pulse` overrides the steady/pulse choice (e.g. "starting" is warning+pulse, "checking" too).
// All pulses collapse to a steady fill under prefers-reduced-motion.

export type StatusTone = "success" | "warning" | "danger" | "idle";

interface StatusDotProps {
  tone: StatusTone;
  pulse?: boolean;
  className?: string;
}

const toneClassName: Record<StatusTone, string> = {
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  idle: "bg-slate-300"
};

export function StatusDot({ tone, pulse = false, className }: StatusDotProps) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${toneClassName[tone]} ${
        pulse ? "motion-safe:animate-pulse" : ""
      } ${className ?? ""}`}
    />
  );
}
