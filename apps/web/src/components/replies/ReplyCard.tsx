"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { statusLabel } from "@/lib/enquiries";

export type Suggestion = {
  id: string;
  enquiry_id: string;
  client_name: string | null;
  pipeline_status: string | null;
  intent: Intent;
  confidence: "high" | "medium" | "low";
  matched: string | null;
  status: string;
  created_at: string;
  message: { id: string; thread_id: string; subject: string; body_text: string | null; sent_at: string } | null;
};

type Intent = "accept" | "change_request" | "decline" | "question" | "other";

const INTENTS: Record<Intent, { label: string; action: string; tone: string }> = {
  accept: { label: "Accepts the quote", action: "Confirm acceptance", tone: "bg-emerald-50 text-emerald-900" },
  change_request: { label: "Asks for changes", action: "Start a revision", tone: "bg-sky-50 text-sky-900" },
  decline: { label: "Declines", action: "Mark as declined", tone: "bg-rose-50 text-rose-900" },
  question: { label: "Has a question", action: "Mark handled", tone: "bg-amber-50 text-amber-900" },
  other: { label: "Nothing to act on", action: "Mark handled", tone: "bg-stone-100 text-stone-700" },
};

export function ReplyCard({ s, onDone, showClient = true }: { s: Suggestion; onDone: () => void; showClient?: boolean }) {
  const [intent, setIntent] = useState<Intent>(s.intent);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(path: string, body?: unknown) {
    setBusy(true);
    setError("");
    try {
      await api(`/replies/${s.id}/${path}`, { method: "POST", body: JSON.stringify(body ?? {}) });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const suggested = INTENTS[s.intent];
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {showClient && (
          <Link href={`/enquiries/${s.enquiry_id}`} className="font-medium text-stone-900 hover:underline">
            {s.client_name}
          </Link>
        )}
        {showClient && s.pipeline_status && <span className="text-stone-500">· {statusLabel(s.pipeline_status)}</span>}
        <span className={`rounded px-2 py-0.5 ${suggested.tone}`}>Suggested: {suggested.label}</span>
        <span className="text-xs text-stone-500">
          {s.confidence} confidence{s.matched ? ` · matched “${s.matched}”` : ""}
        </span>
        {s.message && <span className="ml-auto text-xs text-stone-500">{new Date(s.message.sent_at).toLocaleString()}</span>}
      </div>
      {s.message && <p className="mt-3 whitespace-pre-wrap rounded-md bg-stone-50 p-3 text-sm text-stone-800">{s.message.body_text}</p>}
      {error && <p className="mt-2 text-sm text-rose-800">{error}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <select value={intent} onChange={(ev) => setIntent(ev.target.value as Intent)} className="rounded-md border border-stone-300 px-2 py-1.5">
          {(Object.keys(INTENTS) as Intent[]).map((k) => (
            <option key={k} value={k}>
              {INTENTS[k].label}
            </option>
          ))}
        </select>
        <button
          disabled={busy}
          onClick={() => run("confirm", { intent })}
          className="rounded-md bg-stone-900 px-3 py-1.5 font-medium text-white hover:bg-stone-800 disabled:opacity-40"
        >
          {INTENTS[intent].action}
        </button>
        <button disabled={busy} onClick={() => run("dismiss")} className="rounded-md border border-stone-300 px-3 py-1.5 hover:bg-stone-50">
          Ignore
        </button>
      </div>
    </div>
  );
}
