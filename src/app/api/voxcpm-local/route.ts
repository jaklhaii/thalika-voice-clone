import { NextResponse } from "next/server";
import { spawn } from "node:child_process";
import { openSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { dataDir, ensureDataDirs, logsDir } from "@/lib/file-utils";

export const runtime = "nodejs";

const LOCAL_URL = "http://localhost:7860";
const pidFile = path.join(dataDir, "voxcpm-local.pid");
const projectRoot = process.cwd();
const launcherPath = path.join(projectRoot, "scripts", "voxcpm-local.sh");

async function readPid() {
  try {
    const pid = Number(await fs.readFile(pidFile, "utf8"));
    return Number.isInteger(pid) && pid > 0 ? pid : null;
  } catch {
    return null;
  }
}

function isAlive(pid: number) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function reachable() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1500);
    const response = await fetch(`${LOCAL_URL}/gradio_api/info`, { signal: controller.signal });
    clearTimeout(timeout);
    return response.ok;
  } catch {
    return false;
  }
}

export async function GET() {
  const pid = await readPid();
  const configured = await fs.access(launcherPath).then(() => true).catch(() => false);
  return NextResponse.json({
    configured,
    running: pid ? isAlive(pid) : false,
    reachable: await reachable()
  });
}

export async function POST() {
  if (await reachable()) return NextResponse.json({ started: true, alreadyRunning: true });

  try {
    await fs.access(launcherPath);
  } catch {
    return NextResponse.json(
      { ok: false, error: "The tracked local VoxCPM2 launcher is missing. Reinstall the app." },
      { status: 500 }
    );
  }

  await ensureDataDirs();
  const logFd = openSync(path.join(logsDir, "voxcpm-local.log"), "a");
  // detached + own process group so Stop can kill the whole tree (sh -> python). Survives app
  // restarts; the pidfile is the only handle. Trusts the pidfile — a PID reused after a crash
  // could mistarget the kill; fine for a single local box, add a cmdline check if it bites.
  const child = spawn("bash", [launcherPath], {
    cwd: projectRoot,
    detached: true,
    stdio: ["ignore", logFd, logFd]
  });
  child.unref();
  if (child.pid) await fs.writeFile(pidFile, String(child.pid), "utf8");
  return NextResponse.json({ started: true });
}

export async function DELETE() {
  const pid = await readPid();
  if (pid && isAlive(pid)) {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(pid), "/t", "/f"]);
    } else {
      try {
        process.kill(-pid, "SIGTERM"); // kill the process group
      } catch {
        try {
          process.kill(pid, "SIGTERM");
        } catch {
          /* already gone */
        }
      }
    }
  }
  await fs.rm(pidFile, { force: true });
  return NextResponse.json({ stopped: true });
}
