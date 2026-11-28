"use client";

import { useEffect, useState } from "react";
import { applyTheme, readTheme, THEME_KEY, type ThemeChoice } from "@/lib/theme";

const OPTIONS: { key: ThemeChoice; label: string; icon: string }[] = [
  { key: "light", label: "Light", icon: "☀" },
  { key: "dark", label: "Dark", icon: "☾" },
  { key: "system", label: "Auto", icon: "◐" },
];

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>("system");

  useEffect(() => {
    setChoice(readTheme());
  }, []);

  useEffect(() => {
    if (choice !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [choice]);

  function pick(c: ThemeChoice) {
    setChoice(c);
    localStorage.setItem(THEME_KEY, c);
    applyTheme(c);
  }

  return (
    <div role="radiogroup" aria-label="Colour theme" className="inline-flex rounded-lg border border-stone-200 p-0.5 text-xs">
      {OPTIONS.map((o) => (
        <button
          key={o.key}
          role="radio"
          aria-checked={choice === o.key}
          title={o.key === "system" ? "Follow this computer's setting" : `${o.label} mode`}
          onClick={() => pick(o.key)}
          className={`flex items-center gap-1 rounded-md px-2 py-1 transition-colors ${choice === o.key ? "bg-stone-900 text-white" : "text-stone-500 hover:text-stone-900"}`}
        >
          <span aria-hidden>{o.icon}</span>
          {o.label}
        </button>
      ))}
    </div>
  );
}
