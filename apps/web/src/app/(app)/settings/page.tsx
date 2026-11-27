"use client";

import { useEffect, useState } from "react";
import { RateCards } from "@/components/settings/RateCards";
import { api } from "@/lib/api";

type SessionRow = { id: string; device_label: string | null; ip: string | null; last_seen_at: string; current: boolean };

export default function SettingsPage() {
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
    await api("/auth/logout-everywhere", { method: "POST" });
    window.location.href = "/sign-in";
  }

  return (
    <div className="max-w-4xl">
      <h1 className="font-serif text-2xl text-stone-900">Settings</h1>
      <p className="mt-1 text-stone-600">Templates and business details arrive with Phases 3 to 5.</p>
      <div className="mt-8">
        <RateCards />
      </div>
      <section className="mt-8 rounded-lg border border-stone-200 bg-white">
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3">
          <h2 className="font-medium text-stone-900">Signed-in devices</h2>
          <button onClick={everywhere} className="text-sm text-rose-700 hover:underline">
            Sign out everywhere
          </button>
        </div>
        <ul>
          {sessions.map((s) => (
            <li key={s.id} className="flex items-center justify-between border-b border-stone-100 px-5 py-3 text-sm last:border-0">
              <div>
                <div className="text-stone-900">
                  {s.device_label ?? "Unknown device"} {s.current && <span className="ml-2 rounded bg-rose-50 px-1.5 text-xs text-rose-800">this device</span>}
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
    </div>
  );
}
