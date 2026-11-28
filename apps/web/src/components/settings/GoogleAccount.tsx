"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Status = {
  configured: boolean;
  connected: boolean;
  email?: string;
  send_enabled?: boolean;
  calendar_enabled?: boolean;
  connected_at?: string;
  connected_by?: string;
  last_sync_at?: string | null;
  last_error?: string | null;
};

const OUTCOME: Record<string, string> = {
  connected: "Google account connected. Gmail is read every minute; sending and calendar are off until you switch them on.",
  denied: "Google sign-in was cancelled.",
  expired: "That sign-in took too long or came from another tab. Try again.",
  failed: "Google refused the sign-in. Try again.",
  missing_permissions: "Some permissions were unticked on Google's screen. Connect again and leave every box ticked.",
  not_configured: "Google isn't set up yet: add JSTYLE_GOOGLE_CLIENT_ID and JSTYLE_GOOGLE_CLIENT_SECRET to .env and restart.",
};

export function GoogleAccount() {
  const [s, setS] = useState<Status | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api<Status>("/integrations/google").then(setS).catch(() => setS(null));
  useEffect(() => {
    load();
    const outcome = new URLSearchParams(window.location.search).get("google");
    if (outcome) setNote(OUTCOME[outcome] ?? outcome);
  }, []);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (err) {
      setNote(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(key: "send_enabled" | "calendar_enabled", value: boolean) {
    if (key === "send_enabled" && value && !confirm(`Every email the CRM sends will now go out from ${s?.email}. Continue?`)) return;
    await run(() => api("/integrations/google/options", { method: "PUT", body: JSON.stringify({ [key]: value }) }));
  }

  async function syncNow() {
    setBusy(true);
    try {
      const r = await api<{ attached: number }>("/integrations/google/sync", { method: "POST" });
      setNote(r.attached ? `${r.attached} new client email(s) added to the Inbox.` : "No new client emails.");
      await load();
    } catch (err) {
      setNote(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="google" className="rounded-lg border border-stone-200 bg-white">
      <div className="border-b border-stone-200 px-5 py-3">
        <h2 className="font-medium text-stone-900">Google account (Gmail and Calendar)</h2>
      </div>
      <div className="space-y-4 px-5 py-4 text-sm">
        {note && <p className="rounded-md bg-amber-50 px-3 py-2 text-amber-900">{note}</p>}
        {s && !s.configured && (
          <p className="text-stone-600">
            Google isn&apos;t set up on this server yet. Add the OAuth client ID and secret to <code>.env</code> and restart.
          </p>
        )}
        {s?.configured && !s.connected && (
          <div className="space-y-2">
            <p className="text-stone-600">
              Connect the business Gmail so client replies arrive in the Inbox, emails go out from that address, and weddings appear in its calendar.
            </p>
            <a href="/api/integrations/google/start" className="inline-block rounded-md bg-stone-900 px-3 py-1.5 text-white">
              Connect Google account
            </a>
          </div>
        )}
        {s?.connected && (
          <>
            <div>
              <div className="text-stone-900">
                Connected: <strong>{s.email}</strong>
              </div>
              <div className="text-stone-500">
                Last checked {s.last_sync_at ? new Date(s.last_sync_at).toLocaleString() : "not yet"}
                {s.connected_by && ` · connected by ${s.connected_by}`}
              </div>
              {s.last_error && <div className="mt-1 text-rose-700">Last error: {s.last_error}</div>}
            </div>
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={!!s.send_enabled} disabled={busy} onChange={(ev) => toggle("send_enabled", ev.target.checked)} />
              <span>
                <span className="text-stone-900">Send emails from this account</span>
                <span className="block text-stone-500">Off: emails go to the local test inbox (Mailpit) instead.</span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={!!s.calendar_enabled} disabled={busy} onChange={(ev) => toggle("calendar_enabled", ev.target.checked)} />
              <span>
                <span className="text-stone-900">Add booked weddings and trials to this calendar</span>
                <span className="block text-stone-500">Updates when a date changes; removed if a wedding is cancelled.</span>
              </span>
            </label>
            <div className="flex gap-3">
              <button disabled={busy} onClick={syncNow} className="rounded-md border border-stone-300 px-3 py-1.5 disabled:opacity-40">
                Check Gmail now
              </button>
              <button
                disabled={busy}
                onClick={() => confirm("Disconnect this Google account? The CRM stops reading and sending its mail.") && run(() => api("/integrations/google/disconnect", { method: "POST" }))}
                className="text-rose-700 hover:underline disabled:opacity-40"
              >
                Disconnect
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
