"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function TopNav() {
  const pathname = usePathname();
  const isStudio = pathname === "/" || pathname === "/studio";
  const isLibrary = pathname === "/library";

  return (
    <header className="sticky top-0 z-50 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800/40">
      <div className="max-w-4xl mx-auto px-6 h-12 flex items-center gap-3">
        {/* Mark + wordmark */}
        <div className="flex items-center gap-2 select-none">
          <div className="w-[18px] h-[18px] rounded bg-zinc-100 flex items-center justify-center shrink-0">
            <svg width="9" height="9" viewBox="0 0 10 10" fill="none">
              <path d="M2 5h6M5 2l3 3-3 3" stroke="#09090b" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span className="text-[13px] font-semibold text-zinc-300 tracking-tight">CompeteIQ</span>
        </div>

        <div className="w-px h-3 bg-zinc-800" />

        <nav className="flex items-center gap-0.5">
          <Link
            href="/"
            className={`px-2.5 py-1 rounded text-[13px] font-medium transition-colors duration-100 ${
              isStudio ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/50"
            }`}
          >
            Studio
          </Link>
          <Link
            href="/library"
            className={`px-2.5 py-1 rounded text-[13px] font-medium transition-colors duration-100 ${
              isLibrary ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/50"
            }`}
          >
            Library
          </Link>
        </nav>
      </div>
    </header>
  );
}
