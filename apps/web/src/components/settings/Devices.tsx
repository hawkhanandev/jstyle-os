"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type SessionRow = { id: string; device_label: string | null; ip: string | null; last_seen_at: string; current: boolean };

export function Devices() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const load = () => api<SessionRow[]>("/auth/sessions").then(setSessions).catch(() => setSessions([]));
  useEffect(() => {
    load();
  }, []);

  async function revoke(id: string) {
    await api(`/auth/sessions/${id}`, { method: "DELETE" });
    load();
  }
  async function everywhere() {
    if (!confirm("Sign out on every device, including this one?")) return;
    await api("/auth/logout-everywhere", { method: "POST" });
    window.location.href = "/sign-in";
  }

  return (
    <section className="soft-card rounded-xl border border-stone-200">
      <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3">
        <h2 className="font-medium text-stone-900">Signed-in devices</h2>
        <button onClick={everywhere} className="text-sm text-stone-600 hover:text-stone-900 hover:underline">
          Sign out everywhere
        </button>
      </div>
      <ul>
        {sessions.map((s) => (
          <li key={s.id} className="flex items-center justify-between border-b border-stone-100 px-5 py-3 text-sm last:border-0">
            <div>
              <div className="text-stone-900">
                {s.device_label ?? "Unknown device"} {s.current && <span className="ml-2 rounded bg-stone-100 px-1.5 text-xs text-stone-700">this device</span>}
              </div>
              <div className="text-stone-500">
                {s.ip ?? "unknown IP"} · last seen {new Date(s.last_seen_at).toLocaleString()}
              </div>
            </div>
            {!s.current && (
              <button onClick={() => revoke(s.id)} className="text-stone-600 hover:underline">
                Sign out
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
