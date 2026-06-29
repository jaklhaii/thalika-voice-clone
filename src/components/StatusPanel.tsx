"use client";

import { CheckCircle2, Loader2, Radio, XCircle } from "lucide-react";

export type StudioStatus = "idle" | "saving" | "generating" | "completed" | "failed";

interface StatusPanelProps {
  status: StudioStatus;
  error?: string;
  completedChunks?: number;
  totalChunks?: number;
  progressMessage?: string;
}

const labels: Record<StudioStatus, string> = {
  idle: "Idle",
  saving: "Saving script",
  generating: "Generating audio",
  completed: "Completed",
  failed: "Failed"
};

export function StatusPanel({ status, error, completedChunks, totalChunks, progressMessage }: StatusPanelProps) {
  const Icon = status === "completed" ? CheckCircle2 : status === "failed" ? XCircle : status === "idle" ? Radio : Loader2;
  const total = totalChunks ?? 0;
  const completed = completedChunks ?? 0;
  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const showProgress = status === "generating" && total > 0;

  return (
    <section className="studio-card-bg rounded-[2.2rem] border border-white/10 p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-2xl bg-studio-accent/10 text-studio-accent">
            <Icon size={19} className={status === "saving" || status === "generating" ? "animate-spin" : ""} />
          </div>
          <h2 className="text-lg font-semibold text-studio-text">Status</h2>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            status === "completed"
              ? "bg-emerald-400/15 text-emerald-800"
              : status === "failed"
                ? "bg-red-400/15 text-red-700"
                : "bg-studio-border text-studio-muted"
          }`}
        >
          {labels[status]}
        </span>
      </div>
      <p className="mt-3 text-sm text-studio-muted">
        {status === "idle" && "Waiting for a valid script."}
        {status === "saving" && "Writing Markdown files into local storage."}
        {status === "generating" && (progressMessage || "Generating audio through the selected provider.")}
        {status === "completed" && "Audio is ready for preview and download."}
        {status === "failed" && (error || "Something went wrong.")}
      </p>
      {showProgress && (
        <ChunkProgress completed={completed} total={total} percent={percent} />
      )}
    </section>
  );
}

// Visual chunk cells: each chunk is one cell whose state is derived from the counts. This is the
// "motion-as-teaching" layer — you see *which* chunk is in flight at a glance, instead of parsing
// "Segment 3 of 5". The precise text caption is kept below it for screen readers + exact reading.
//
// State derivation (no new props needed):
//   - index < completed            -> done (filled)
//   - index === completed          -> in flight (pulsing)
//   - index > completed            -> queued (faint)
// Only renders during `generating`; on failure the panel's error text takes over instead.
//
// Cap visible cells at 12 so a 50-chunk script doesn't render 50 cells. Past the cap we render
// proportional grouped segments (still visually informative, no layout blowup). Respects
// prefers-reduced-motion: the in-flight pulse collapses to a steady accent fill.
const MAX_VISIBLE_CELLS = 12;

interface ChunkProgressProps {
  completed: number;
  total: number;
  percent: number;
}

function ChunkProgress({ completed, total, percent }: ChunkProgressProps) {
  // Build the per-chunk state list, then down-sample to MAX_VISIBLE_CELLS if needed.
  type CellState = "done" | "active" | "queued";
  const fullStates: CellState[] = [];
  for (let i = 0; i < total; i += 1) {
    if (i < completed) fullStates.push("done");
    else if (i === completed) fullStates.push("active");
    else fullStates.push("queued");
  }

  const cells = downsampleStates(fullStates, MAX_VISIBLE_CELLS);

  return (
    <div className="mt-4 grid gap-2">
      <div className="flex gap-1.5" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={`Segment ${Math.min(completed + 1, total)} of ${total}`}>
        {cells.map((state, index) => (
          <span
            key={index}
            title={cellTitle(state)}
            className={`h-2.5 flex-1 rounded-full transition-colors duration-300 ${cellClassName(state)}`}
          />
        ))}
      </div>
      <span className="text-xs font-medium text-studio-muted">
        Segment {Math.min(completed + 1, total)} of {total} · {percent}%
      </span>
    </div>
  );
}

function cellClassName(state: "done" | "active" | "queued") {
  if (state === "done") return "bg-studio-accent";
  if (state === "active") {
    // Pulses under normal motion; holds a steady strong accent when the user prefers reduced motion.
    return "bg-studio-accent/50 motion-safe:animate-pulse";
  }
  return "bg-studio-border";
}

function cellTitle(state: "done" | "active" | "queued") {
  if (state === "done") return "Done";
  if (state === "active") return "Generating";
  return "Queued";
}

// Down-sample a state list to at most `max` cells by merging neighbors. The merge rule preserves
// the worst (most-progressed) state in each bucket so the in-flight cell is never hidden: a bucket
// containing any "active" reads as active; else any "done" reads as done; else queued.
function downsampleStates(states: ("done" | "active" | "queued")[], max: number) {
  if (states.length <= max) return states;

  const out: ("done" | "active" | "queued")[] = [];
  const bucketSize = states.length / max;
  for (let i = 0; i < max; i += 1) {
    const start = Math.floor(i * bucketSize);
    const end = Math.max(start + 1, Math.floor((i + 1) * bucketSize));
    const bucket = states.slice(start, end);
    out.push(bucket.includes("active") ? "active" : bucket.includes("done") ? "done" : "queued");
  }
  return out;
}
