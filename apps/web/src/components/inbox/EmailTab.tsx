"use client";

import { useCallback, useEffect, useState } from "react";
import { Conversation } from "@/components/inbox/Conversation";
import { api, ApiError } from "@/lib/api";
import { type ThreadSummary, when } from "@/lib/inbox";
import { ReplyCard, type Suggestion } from "@/components/replies/ReplyCard";

export function EmailTab({ enquiryId, onChange }: { enquiryId: string; onChange?: () => void }) {
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [local, setLocal] = useState(false);
  const [sim, setSim] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(
    () =>
      Promise.all([
        api<ThreadSummary[]>(`/threads?enquiry_id=${enquiryId}`),
        api<Suggestion[]>(`/replies?enquiry_id=${enquiryId}`),
      ]).then(([ts, ss]) => {
        setThreads(ts);
        setSuggestions(ss);
        setSelected((cur) => cur ?? ts[0]?.id ?? null);
      }),
    [enquiryId],
  );
  useEffect(() => {
    load().catch(() => setError("Could not load emails."));
    fetch("/api/auth/config")
      .then((r) => r.json())
      .then((c) => setLocal(Boolean(c.dev_login)))
      .catch(() => undefined);
  }, [load]);

  async function simulate() {
    setError("");
    try {
      await api(`/dev/enquiries/${enquiryId}/simulate-reply`, { method: "POST", body: JSON.stringify({ body: sim }) });
      setSim("");
      setSelected(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not simulate.");
    }
  }

  if (!threads) return <p className="mt-6 text-stone-500">{error || "Loading…"}</p>;
  return (
    <div className="mt-6 space-y-4">
      {error && <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      {suggestions.map((s) => (
        <ReplyCard
          key={s.id}
          s={s}
          showClient={false}
          onDone={() => {
            load();
            onChange?.();
          }}
        />
      ))}
      {threads.length === 0 && <p className="text-stone-500">No emails with this client yet.</p>}
      {threads.length > 1 && (
        <div className="flex flex-wrap gap-2 text-sm">
          {threads.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelected(t.id)}
              className={`rounded-md border px-3 py-1 ${selected === t.id ? "border-rose-300 bg-rose-50" : "border-stone-300 bg-white"}`}
            >
              {t.subject} · {when(t.last_message_at)}
            </button>
          ))}
        </div>
      )}
      {selected && (
        <div className="h-[36rem] overflow-hidden rounded-lg border border-stone-200 bg-white">
          <Conversation threadId={selected} onChange={load} showClient={false} />
        </div>
      )}
      {local && (
        <div className="rounded-lg border border-dashed border-amber-300 bg-amber-50 p-4 text-sm">
          <p className="font-medium text-amber-900">Local testing: pretend the client replied</p>
          <p className="text-amber-800">Until Gmail is connected, use this to test how replies show up.</p>
          <textarea value={sim} onChange={(ev) => setSim(ev.target.value)} rows={2} className="mt-2 w-full rounded-md border border-amber-300 px-2 py-1.5" />
          <button disabled={!sim.trim()} onClick={simulate} className="mt-2 rounded-md border border-amber-400 bg-white px-3 py-1.5 text-amber-900 disabled:opacity-40">
            Add client reply
          </button>
        </div>
      )}
    </div>
  );
}
