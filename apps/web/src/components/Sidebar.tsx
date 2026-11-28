"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV } from "@/lib/nav";

export function Sidebar({ current }: { current: number }) {
  const path = usePathname();
  return (
    <aside className="ink-gradient sticky top-0 flex h-screen w-60 shrink-0 flex-col px-3 py-6 text-snow">
      <div className="px-3 pb-8">
        <div className="font-serif text-2xl tracking-wide">Jstyle</div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-snow/50">Business OS</div>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto">
        {NAV.map((group) => (
          <div key={group.section}>
            <div className="px-3 pb-1.5 text-[10px] font-medium uppercase tracking-[0.2em] text-snow/40">{group.section}</div>
            {group.items.map((item) => {
              const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
              const ready = item.phase <= current;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center justify-between rounded-md px-3 py-1.5 text-sm transition-colors ${
                    active ? "bg-snow text-ink shadow-sm" : "text-snow/75 hover:bg-snow/10 hover:text-snow"
                  }`}
                >
                  <span>{item.label}</span>
                  {!ready && <span className="text-[10px] text-snow/40">P{item.phase}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="px-3 pt-4 text-[10px] uppercase tracking-[0.2em] text-snow/30">Hawaii · Oregon</div>
    </aside>
  );
}
