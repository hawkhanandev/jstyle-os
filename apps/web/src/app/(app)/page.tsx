"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate, REGION_NAMES } from "@/lib/enquiries";
import { fmt } from "@/lib/money";

type Region = {
  open_enquiries: number;
  new_this_month: number;
  quotes_with_clients: number;
  upcoming_weddings: number;
  booked_this_year: number;
  booked_value_cents: number;
  outstanding_cents: number;
  next_wedding: { enquiry_id: string; client_name: string; date: string } | null;
};

type Dash = {
  counts: Record<string, number>;
  regions: { HI: Region; OR: Region };
  upcoming_weddings: { enquiry_id: string; client_name: string; date: string; venue: string | null; region: "HI" | "OR" | null }[];
  open_tasks: { id: string; title: string; kind: string; entity_type: string; entity_id: string; due_at: string | null }[];
};

const ACTIONS: [string, string, string][] = [
  ["new_enquiries", "New enquiries", "/enquiries"],
  ["quotes_awaiting_approval", "Quotes to approve", "/approvals"],
  ["replies_to_review", "Replies to review", "/replies"],
  ["awaiting_signed_contract", "Waiting on contract or deposit", "/contracts"],
  ["payments_to_verify", "Payments to verify", "/payments"],
  ["held_submissions", "Held form submissions", "/forms"],
  ["failed_automations", "Failed automations", "/settings#activity"],
];

const ISLAND: Record<"HI" | "OR", string> = { HI: "Hawaii time", OR: "Pacific time" };

function RegionCard({ code, r }: { code: "HI" | "OR"; r: Region }) {
  const stats: [string, string | number][] = [
    ["Open enquiries", r.open_enquiries],
    ["New this month", r.new_this_month],
    ["Quotes with clients", r.quotes_with_clients],
    ["Upcoming weddings", r.upcoming_weddings],
  ];
  return (
    <section className="soft-card overflow-hidden rounded-2xl border border-stone-200">
      <div className="ink-gradient px-6 py-5 text-snow">
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif text-3xl">{REGION_NAMES[code]}</h2>
          <Link href={`/enquiries?region=${code}`} className="text-xs uppercase tracking-[0.2em] text-snow/60 hover:text-snow">
            View enquiries
          </Link>
        </div>
        <div className="text-xs uppercase tracking-[0.2em] text-snow/40">{ISLAND[code]}</div>
        <div className="mt-5 grid grid-cols-2 gap-6">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-snow/50">Booked, upcoming</div>
            <div className="mt-1 text-2xl font-light">{fmt(r.booked_value_cents)}</div>
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-snow/50">Still owed</div>
            <div className="mt-1 text-2xl font-light">{fmt(r.outstanding_cents)}</div>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 divide-x divide-y divide-stone-100 border-b border-stone-100 sm:grid-cols-4 sm:divide-y-0">
        {stats.map(([label, v]) => (
          <div key={label} className="px-5 py-4">
            <div className={`text-2xl font-semibold ${v ? "text-stone-900" : "text-stone-300"}`}>{v}</div>
            <div className="mt-0.5 text-xs text-stone-500">{label}</div>
          </div>
        ))}
      </div>
      <div className="px-6 py-3 text-sm text-stone-600">
        {r.next_wedding ? (
          <Link href={`/enquiries/${r.next_wedding.enquiry_id}`} className="hover:underline">
            Next wedding: <b className="text-stone-900">{formatDate(r.next_wedding.date)}</b> · {r.next_wedding.client_name}
          </Link>
        ) : (
          <span className="text-stone-400">No upcoming weddings booked yet.</span>
        )}
        <span className="float-right text-stone-400">{r.booked_this_year} booked this year</span>
      </div>
    </section>
  );
}

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

  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const todo = ACTIONS.filter(([k]) => (d?.counts[k] ?? 0) > 0);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.25em] text-stone-400">{today}</div>
          <h1 className="mt-1 font-serif text-4xl text-stone-900">Good to see you</h1>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-wider text-stone-400">Outstanding balances</div>
          <div className="text-2xl font-light text-stone-900">{fmt(d?.counts.outstanding_balances_cents ?? 0)}</div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        {d ? (
          <>
            <RegionCard code="HI" r={d.regions.HI} />
            <RegionCard code="OR" r={d.regions.OR} />
          </>
        ) : (
          <div className="col-span-2 h-64 animate-pulse rounded-2xl bg-stone-100" />
        )}
      </div>

      <section>
        <h2 className="text-xs font-medium uppercase tracking-[0.2em] text-stone-400">Needs your attention</h2>
        {d && todo.length === 0 && <p className="mt-3 text-sm text-stone-500">All clear. Nothing is waiting on you.</p>}
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {todo.map(([key, label, href]) => (
            <Link key={key} href={href} className="soft-card group rounded-xl border border-stone-200 px-4 py-3 transition hover:border-stone-900">
              <div className="text-2xl font-semibold text-stone-900">{d?.counts[key]}</div>
              <div className="text-sm text-stone-500 group-hover:text-stone-900">{label}</div>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="soft-card rounded-2xl border border-stone-200 p-6">
          <h2 className="font-serif text-xl text-stone-900">Upcoming weddings</h2>
          {d?.upcoming_weddings.length === 0 && <p className="mt-3 text-sm text-stone-500">No booked weddings yet.</p>}
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {d?.upcoming_weddings.map((w) => (
              <li key={w.enquiry_id} className="py-2">
                <Link href={`/enquiries/${w.enquiry_id}`} className="flex items-center justify-between gap-3 hover:underline">
                  <span>
                    <b className="text-stone-900">{formatDate(w.date)}</b> · {w.client_name}
                    {w.venue && <span className="text-stone-500"> · {w.venue}</span>}
                  </span>
                  {w.region && <span className="shrink-0 rounded-full border border-stone-300 px-2 py-px text-[11px] text-stone-600">{REGION_NAMES[w.region]}</span>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
        <section className="soft-card rounded-2xl border border-stone-200 p-6">
          <h2 className="font-serif text-xl text-stone-900">Tasks</h2>
          {d?.open_tasks.length === 0 && <p className="mt-3 text-sm text-stone-500">Nothing to do.</p>}
          <ul className="mt-3 divide-y divide-stone-100 text-sm">
            {d?.open_tasks.map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-3 py-2">
                {t.entity_type === "enquiry" ? (
                  <Link href={`/enquiries/${t.entity_id}`} className="hover:underline">
                    {t.title}
                  </Link>
                ) : (
                  <span>{t.title}</span>
                )}
                <button onClick={() => done(t.id)} className="shrink-0 rounded-md border border-stone-300 px-2 py-0.5 text-xs text-stone-600 hover:border-stone-900 hover:text-stone-900">
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
