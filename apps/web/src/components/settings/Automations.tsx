"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Event = {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  last_error: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

const COLORS: Record<string, string> = {
  done: "bg-emerald-50 text-emerald-800",
  pending: "bg-stone-100 text-stone-700",
  in_progress: "bg-sky-50 text-sky-800",
  failed: "bg-rose-50 text-rose-800",
  dead: "bg-rose-100 text-rose-900",
  paused: "bg-amber-50 text-amber-800",
};

export function Automations() {
  const [events, setEvents] = useState<Event[]>([]);
  const load = () =>
    api<Event[]>("/outbox")
      .then(setEvents)
      .catch(() => setEvents([]));
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  async function act(id: string, action: "retry" | "cancel") {
    await api(`/outbox/${id}/${action}`, { method: "POST" });
    load();
  }

  return (
    <section className="rounded-lg border border-stone-200 bg-white">
      <div className="border-b border-stone-200 px-5 py-3">
        <h2 className="font-medium text-stone-900">Automation log</h2>
        <p className="text-sm text-stone-500">Every email and background job. Failed ones can be retried or cancelled.</p>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {events.length === 0 && (
            <tr>
              <td className="px-5 py-4 text-stone-500">Nothing yet.</td>
            </tr>
          )}
          {events.slice(0, 30).map((e) => (
            <tr key={e.id} className="border-b border-stone-100 last:border-0">
              <td className="px-5 py-2 text-stone-500">{new Date(e.created_at).toLocaleString()}</td>
              <td className="px-2 py-2">
                {e.kind}
                {typeof e.payload.template === "string" && <span className="text-stone-500"> · {e.payload.template}</span>}
              </td>
              <td className="px-2 py-2">
                <span className={`rounded px-1.5 text-xs ${COLORS[e.status] ?? ""}`}>{e.status}</span>
                {e.attempts > 1 && <span className="ml-1 text-xs text-stone-400">{e.attempts} tries</span>}
              </td>
              <td className="max-w-xs truncate px-2 py-2 text-xs text-stone-500" title={e.last_error ?? ""}>
                {e.last_error}
              </td>
              <td className="px-5 py-2 text-right">
                {["failed", "dead", "paused"].includes(e.status) && (
                  <button onClick={() => act(e.id, "retry")} className="text-rose-700 hover:underline">
                    Retry
                  </button>
                )}
                {["pending", "failed", "paused"].includes(e.status) && (
                  <button onClick={() => act(e.id, "cancel")} className="ml-3 text-stone-500 hover:underline">
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
