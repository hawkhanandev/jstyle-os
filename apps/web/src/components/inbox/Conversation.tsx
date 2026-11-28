"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { statusLabel } from "@/lib/enquiries";
import { type Message, type Thread } from "@/lib/inbox";

export function Conversation({ threadId, onChange, showClient = true }: { threadId: string; onChange?: () => void; showClient?: boolean }) {
  const [t, setT] = useState<Thread | null>(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => api<Thread>(`/threads/${threadId}`).then(setT), [threadId]);
  useEffect(() => {
    setT(null);
    load()
      .then(() => api(`/threads/${threadId}/read`, { method: "POST" }))
      .then(() => onChange?.())
      .catch(() => setError("Could not load the conversation."));
    // onChange is a callback from the parent; reloading on its identity would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, load]);

  // While a reply is going out, refresh until the worker has sent it.
  useEffect(() => {
    if (!t?.replies_sending) return;
    const timer = setTimeout(() => load().then(() => onChange?.()), 2500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, load]);

  async function send() {
    setBusy(true);
    setError("");
    try {
      await api(`/threads/${threadId}/reply`, { method: "POST", body: JSON.stringify({ body }) });
      setBody("");
      await load();
      onChange?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send.");
    } finally {
      setBusy(false);
    }
  }

  async function markUnread() {
    await api(`/threads/${threadId}/unread`, { method: "POST" });
    onChange?.();
  }

  if (!t) return <p className="p-6 text-stone-500">{error || "Loading…"}</p>;
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-stone-200 px-5 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-medium text-stone-900">{t.subject}</h2>
            {showClient && t.enquiry_id && (
              <p className="text-sm text-stone-600">
                <Link href={`/enquiries/${t.enquiry_id}`} className="hover:underline">
                  {t.client_name}
                </Link>{" "}
                · {t.client_email} · {t.pipeline_status ? statusLabel(t.pipeline_status) : ""}
              </p>
            )}
          </div>
          <button onClick={markUnread} className="shrink-0 text-sm text-stone-500 hover:underline">
            Mark unread
          </button>
        </div>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto bg-stone-50 p-5">
        {t.messages.map((m) => (
          <Bubble key={m.id} m={m} />
        ))}
        {t.replies_sending > 0 && <p className="text-right text-sm text-stone-500">Sending your reply…</p>}
      </div>
      <div className="border-t border-stone-200 bg-white p-4">
        {error && <p className="mb-2 text-sm text-rose-800">{error}</p>}
        <textarea
          value={body}
          onChange={(ev) => setBody(ev.target.value)}
          rows={4}
          placeholder={`Reply to ${t.client_name ?? "the client"}…`}
          className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
        />
        <div className="mt-2 flex justify-end">
          <button
            disabled={busy || !body.trim()}
            onClick={send}
            className="rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-40"
          >
            Send reply
          </button>
        </div>
      </div>
    </div>
  );
}

function Bubble({ m }: { m: Message }) {
  const [open, setOpen] = useState(true);
  const mine = m.direction === "outbound";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div className={`w-full max-w-2xl rounded-lg border ${mine ? "border-rose-100 bg-white" : "border-stone-200 bg-white"}`}>
        <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-xs text-stone-500">
          <span>
            <b className="text-stone-700">{mine ? "You" : m.from_addr}</b>
            {m.template_key && <span> · automatic: {m.template_key.replaceAll("_", " ")}</span>}
          </span>
          <span>{new Date(m.sent_at).toLocaleString()}</span>
        </button>
        {open &&
          (m.body_html ? (
            <iframe
              title={m.subject}
              sandbox=""
              srcDoc={`<base target="_blank"><style>body{font-family:system-ui,sans-serif;font-size:14px;color:#292524;margin:0 16px 12px}</style>${m.body_html}`}
              className="h-64 w-full rounded bg-snow"
            />
          ) : (
            <p className="whitespace-pre-wrap px-4 pb-3 text-sm text-stone-800">{m.body_text}</p>
          ))}
      </div>
    </div>
  );
}
