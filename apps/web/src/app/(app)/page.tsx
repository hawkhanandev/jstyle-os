"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/enquiries";
import { fmt } from "@/lib/money";

type Dash = {
  counts: Record<string, number>;
  upcoming_weddings: { enquiry_id: string; client_name: string; date: string; venue: string | null }[];
  open_tasks: { id: string; title: string; kind: string; entity_type: string; entity_id: string; due_at: string | null }[];
};

const TILES: [string, string, string][] = [
  ["new_enquiries", "New enquiries", "/pipeline"],
  ["quotes_awaiting_approval", "Quotes awaiting approval", "/approvals"],
  ["quotes_sent", "Quotes with clients", "/pipeline"],
  ["replies_to_review", "Replies to review", "/replies"],
  ["awaiting_signed_contract", "Waiting for contract or deposit", "/contracts"],
  ["payments_to_verify", "Payments to verify", "/payments"],
  ["outstanding_balances_cents", "Outstanding balances", "/invoices"],
  ["held_submissions", "Held form submissions", "/forms"],
  ["failed_automations", "Failed automations", "/settings"],
];

export default function Dashboard() {
  const [d, setD] = useState<Dash | null>(null);
  const load = () => api<Dash>("/dashboard").then(setD).catch(() => setD(null));
  useEffect(() => {
    load();
  }, []);

  async function done(id: string) {
    await api(`/tasks/${id}/done`, { method: "POST" });
    load();
  }

  return (
    <div>
      <h1 className="font-serif text-2xl text-stone-900">Dashboard</h1>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {TILES.map(([key, label, href]) => {
          const v = d?.counts[key] ?? 0;
          return (
            <Link key={key} href={href} className="rounded-lg border border-stone-200 bg-white p-5 hover:border-stone-300">
              <div className="text-sm text-stone-500">{label}</div>
              <div className={`mt-2 text-3xl font-semibold ${v ? "text-stone-900" : "text-stone-300"}`}>{key.endsWith("_cents") ? fmt(v) : v}</div>
            </Link>
          );
        })}
      </div>
      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-stone-200 bg-white p-5">
          <h2 className="font-medium">Upcoming weddings</h2>
          {d?.upcoming_weddings.length === 0 && <p className="mt-2 text-sm text-stone-500">No booked weddings yet.</p>}
          <ul className="mt-2 space-y-1 text-sm">
            {d?.upcoming_weddings.map((w) => (
              <li key={w.enquiry_id}>
                <Link href={`/enquiries/${w.enquiry_id}`} className="hover:underline">
                  <b>{formatDate(w.date)}</b> · {w.client_name}
                  {w.venue && <span className="text-stone-500"> · {w.venue}</span>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
        <section className="rounded-lg border border-stone-200 bg-white p-5">
          <h2 className="font-medium">Tasks</h2>
          {d?.open_tasks.length === 0 && <p className="mt-2 text-sm text-stone-500">Nothing to do.</p>}
          <ul className="mt-2 space-y-1 text-sm">
            {d?.open_tasks.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3">
                {t.entity_type === "enquiry" ? (
                  <Link href={`/enquiries/${t.entity_id}`} className="hover:underline">
                    {t.title}
                  </Link>
                ) : (
                  <span>{t.title}</span>
                )}
                <button onClick={() => done(t.id)} className="shrink-0 text-stone-500 hover:underline">
                  Done
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
