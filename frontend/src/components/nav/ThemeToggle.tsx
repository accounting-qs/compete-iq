"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="w-[102px] h-[28px]" />; // Placeholder to prevent layout shift
  }

  return (
    <div className="flex items-center bg-zinc-100/50 dark:bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/40 rounded-lg p-0.5 ml-4">
      <button
        onClick={() => setTheme("light")}
        className={`flex items-center justify-center w-8 h-[22px] rounded-md transition-colors ${
          theme === "light"
            ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-100 dark:bg-zinc-800 dark:text-zinc-900 dark:text-zinc-100 dark:shadow-none"
            : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-800 dark:text-zinc-300"
        }`}
        title="Light Mode"
      >
        <Sun className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={() => setTheme("dark")}
        className={`flex items-center justify-center w-8 h-[22px] rounded-md transition-colors ${
          theme === "dark"
            ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-100 dark:bg-zinc-800 dark:text-zinc-900 dark:text-zinc-100 dark:shadow-none"
            : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-800 dark:text-zinc-300"
        }`}
        title="Dark Mode"
      >
        <Moon className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={() => setTheme("system")}
        className={`flex items-center justify-center w-8 h-[22px] rounded-md transition-colors ${
          theme === "system"
            ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-100 dark:bg-zinc-800 dark:text-zinc-900 dark:text-zinc-100 dark:shadow-none"
            : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-800 dark:text-zinc-300"
        }`}
        title="System Preference"
      >
        <Monitor className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
