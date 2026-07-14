"use client";

import { FileText, FolderOpen, History, Mic2 } from "lucide-react";
import Link from "next/link";

interface AppHeaderProps {
  activeTab: "script" | "voiceover" | "history" | "storage";
}

export function AppHeader({ activeTab }: AppHeaderProps) {
  const tabClass = (tab: AppHeaderProps["activeTab"]) =>
    `inline-flex min-w-0 items-center justify-center gap-1 rounded-[1.35rem] px-2 py-2 text-xs font-semibold transition sm:gap-2 sm:px-4 sm:text-sm ${
      activeTab === tab
        ? "border border-studio-accent/25 bg-studio-accent/10 text-emerald-800 shadow-sm shadow-emerald-100"
        : "text-studio-muted hover:bg-white/7 hover:text-studio-text"
    }`;

  return (
    <nav className="flex min-w-0 flex-col gap-3 rounded-[2rem] sm:flex-row sm:items-center sm:justify-start">
      <div className="studio-card-bg grid w-full min-w-0 grid-cols-4 items-center gap-1 rounded-[1.95rem] border border-white/10 p-1 sm:flex sm:w-auto">
        <Link href="/script" className={tabClass("script")} prefetch>
          <FileText size={16} />
          Script
        </Link>
        <Link href="/" className={tabClass("voiceover")} prefetch>
          <Mic2 size={16} />
          Voice Over
        </Link>
        <Link href="/history" className={tabClass("history")} prefetch>
          <History size={16} />
          History
        </Link>
        <Link href="/storage" className={tabClass("storage")} prefetch>
          <FolderOpen size={16} />
          Folders
        </Link>
      </div>
    </nav>
  );
}
