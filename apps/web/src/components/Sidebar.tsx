"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV } from "@/lib/nav";

export function Sidebar({ current }: { current: number }) {
  const path = usePathname();
  return (
    <aside className="w-60 shrink-0 border-r border-stone-200 bg-white px-3 py-5">
      <div className="px-3 pb-6">
        <div className="font-serif text-xl text-stone-900">Jstyle</div>
        <div className="text-xs uppercase tracking-widest text-stone-500">Business OS</div>
      </div>
      <nav className="space-y-6">
        {NAV.map((group) => (
          <div key={group.section}>
            <div className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-stone-400">{group.section}</div>
            {group.items.map((item) => {
              const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
              const ready = item.phase <= current;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center justify-between rounded-md px-3 py-1.5 text-sm ${
                    active ? "bg-rose-50 font-medium text-rose-900" : "text-stone-700 hover:bg-stone-100"
                  }`}
                >
                  <span>{item.label}</span>
                  {!ready && <span className="text-[10px] text-stone-400">P{item.phase}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
