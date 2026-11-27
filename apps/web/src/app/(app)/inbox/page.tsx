"use client";

import { useCallback, useEffect, useState } from "react";
import { Conversation } from "@/components/inbox/Conversation";
import { api } from "@/lib/api";
import { type ThreadSummary, when } from "@/lib/inbox";

export default function InboxPage() {
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(
    () =>
      api<ThreadSummary[]>(`/threads${unreadOnly ? "?unread=true" : ""}`)
        .then(setThreads)
        .catch(() => setError("Could not load the inbox.")),
    [unreadOnly],
  );
  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div>
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-serif text-3xl text-stone-900">Inbox</h1>
          <p className="mt-1 text-stone-600">Conversations with brides and planners. Other email stays in Gmail.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-stone-600">
          <input type="checkbox" checked={unreadOnly} onChange={(ev) => setUnreadOnly(ev.target.checked)} />
          Unread only
        </label>
      </div>
      {error && <p className="mt-3 rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      <div className="mt-6 grid h-[calc(100vh-12rem)] grid-cols-1 overflow-hidden rounded-lg border border-stone-200 bg-white md:grid-cols-[22rem_1fr]">
        <ul className="overflow-y-auto border-r border-stone-200">
          {threads?.length === 0 && <li className="p-6 text-sm text-stone-500">No conversations yet.</li>}
          {threads?.map((t) => (
            <li key={t.id}>
              <button
                onClick={() => setSelected(t.id)}
                className={`block w-full border-b border-stone-100 px-4 py-3 text-left ${selected === t.id ? "bg-rose-50" : "hover:bg-stone-50"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`truncate ${t.unread ? "font-semibold text-stone-900" : "text-stone-700"}`}>
                    {t.unread && <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-rose-700" />}
                    {t.client_name ?? t.client_email}
                  </span>
                  <span className="shrink-0 text-xs text-stone-500">{when(t.last_message_at)}</span>
                </div>
                <div className="truncate text-sm text-stone-600">{t.subject}</div>
                <div className="truncate text-xs text-stone-500">
                  {t.last_direction === "outbound" ? "You: " : ""}
                  {t.snippet}
                </div>
              </button>
            </li>
          ))}
        </ul>
        <div className="min-h-0">
          {selected ? (
            <Conversation threadId={selected} onChange={load} />
          ) : (
            <p className="p-6 text-sm text-stone-500">Choose a conversation.</p>
          )}
        </div>
      </div>
    </div>
  );
}
