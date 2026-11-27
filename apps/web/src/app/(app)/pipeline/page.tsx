"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { CLOSED, type Enquiry, FLAG_LABELS, formatDate, REGION_NAMES, STAGES, statusLabel } from "@/lib/enquiries";

type View = "board" | "table";

export default function PipelinePage() {
  const [rows, setRows] = useState<Enquiry[]>([]);
  const [region, setRegion] = useState("");
  const [q, setQ] = useState("");
  const [view, setView] = useState<View>("board");
  const [showClosed, setShowClosed] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams();
    if (region) params.set("region", region);
    if (q) params.set("q", q);
    const t = setTimeout(() => {
      api<Enquiry[]>(`/enquiries?${params}`)
        .then(setRows)
        .catch(() => setRows([]));
    }, 200);
    return () => clearTimeout(t);
  }, [region, q]);

  const columns = useMemo(() => (showClosed ? [...STAGES, ...CLOSED] : STAGES), [showClosed]);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl text-stone-900">Pipeline</h1>
          <p className="mt-1 text-stone-600">{rows.length} enquiries</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <input
            placeholder="Search name, email, venue"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-56 rounded-md border border-stone-300 px-2 py-1.5"
          />
          <select value={region} onChange={(e) => setRegion(e.target.value)} className="rounded-md border border-stone-300 px-2 py-1.5">
            <option value="">All regions</option>
            <option value="HI">Hawaii</option>
            <option value="OR">Oregon</option>
          </select>
          <label className="flex items-center gap-1 text-stone-600">
            <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> Closed
          </label>
          <div className="flex overflow-hidden rounded-md border border-stone-300">
            {(["board", "table"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1.5 capitalize ${view === v ? "bg-stone-900 text-white" : "bg-white"}`}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
      </div>

      {view === "board" ? (
        <div className="mt-6 flex gap-3 overflow-x-auto pb-4">
          {columns.map((col) => {
            const items = rows.filter((r) => r.pipeline_status === col.key);
            return (
              <div key={col.key} className="w-64 shrink-0 rounded-lg bg-stone-100 p-2">
                <div className="flex justify-between px-1 pb-2 text-xs font-medium uppercase tracking-wide text-stone-500">
                  <span>{col.label}</span>
                  <span>{items.length}</span>
                </div>
                <div className="space-y-2">
                  {items.map((e) => (
                    <Card key={e.id} e={e} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <table className="mt-6 w-full overflow-hidden rounded-lg border border-stone-200 bg-white text-sm">
          <thead className="bg-stone-50 text-left text-stone-500">
            <tr>
              <th className="px-4 py-2">Client</th>
              <th className="px-4 py-2">Wedding date</th>
              <th className="px-4 py-2">Region</th>
              <th className="px-4 py-2">Venue</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className="border-t border-stone-100 hover:bg-stone-50">
                <td className="px-4 py-2">
                  <Link href={`/enquiries/${e.id}`} className="font-medium text-stone-900 hover:underline">
                    {e.client_name}
                  </Link>
                  {e.type === "planner" && <span className="ml-2 text-xs text-violet-700">Planner</span>}
                </td>
                <td className="px-4 py-2">{formatDate(e.wedding_date)}</td>
                <td className="px-4 py-2">{e.region ? REGION_NAMES[e.region] : "Unknown"}</td>
                <td className="px-4 py-2 text-stone-600">{e.venue_name}</td>
                <td className="px-4 py-2">{statusLabel(e.pipeline_status)}</td>
                <td className="px-4 py-2 text-amber-700">{e.needs_review_flags.map((f) => FLAG_LABELS[f] ?? f).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Card({ e }: { e: Enquiry }) {
  return (
    <Link href={`/enquiries/${e.id}`} className="block rounded-md border border-stone-200 bg-white p-3 text-sm shadow-sm hover:border-rose-300">
      <div className="flex items-center justify-between">
        <span className="font-medium text-stone-900">{e.client_name}</span>
        <span className="rounded bg-stone-100 px-1.5 text-xs text-stone-600">{e.region ?? "?"}</span>
      </div>
      <div className="mt-1 text-stone-500">{formatDate(e.wedding_date)}</div>
      {e.venue_name && <div className="truncate text-stone-500">{e.venue_name}</div>}
      <div className="mt-2 flex flex-wrap gap-1">
        {e.type === "planner" && <span className="rounded bg-violet-50 px-1.5 text-xs text-violet-800">Planner</span>}
        {e.needs_review_flags.map((f) => (
          <span key={f} className="rounded bg-amber-50 px-1.5 text-xs text-amber-800">
            {FLAG_LABELS[f] ?? f}
          </span>
        ))}
      </div>
    </Link>
  );
}
