"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { CLOSED, type Enquiry, FLAG_LABELS, formatDate, REGION_NAMES, statusLabel } from "@/lib/enquiries";

const GROUPS = [
  { key: "open", label: "Open" },
  { key: "booked", label: "Booked" },
  { key: "closed", label: "Closed" },
  { key: "all", label: "All" },
] as const;
type Group = (typeof GROUPS)[number]["key"];
type Sort = "received" | "wedding";

const closedKeys = new Set(CLOSED.map((c) => c.key));
const inGroup = (e: Enquiry, g: Group) =>
  g === "all" ? true : g === "booked" ? e.pipeline_status === "BOOKED" : g === "closed" ? closedKeys.has(e.pipeline_status) : e.pipeline_status !== "BOOKED" && !closedKeys.has(e.pipeline_status);

function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { key: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-stone-200 bg-white p-0.5 text-sm">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`rounded-md px-3 py-1 transition-colors ${value === o.key ? "bg-stone-900 text-white" : "text-stone-600 hover:text-stone-900"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function EnquiriesPage() {
  const [rows, setRows] = useState<Enquiry[] | null>(null);
  const [region, setRegion] = useState<"" | "HI" | "OR">("");
  useEffect(() => {
    const r = new URLSearchParams(window.location.search).get("region");
    if (r === "HI" || r === "OR") setRegion(r);
  }, []);
  const [type, setType] = useState<"" | "bride" | "planner">("");
  const [group, setGroup] = useState<Group>("open");
  const [sort, setSort] = useState<Sort>("received");
  const [q, setQ] = useState("");

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

  const shown = useMemo(() => {
    const list = (rows ?? []).filter((e) => inGroup(e, group) && (!type || e.type === type));
    return [...list].sort((a, b) =>
      sort === "received" ? b.created_at.localeCompare(a.created_at) : (a.wedding_date ?? "9999").localeCompare(b.wedding_date ?? "9999"),
    );
  }, [rows, group, type, sort]);

  const counts = useMemo(() => Object.fromEntries(GROUPS.map((g) => [g.key, (rows ?? []).filter((e) => inGroup(e, g.key)).length])), [rows]);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl text-stone-900">Enquiries</h1>
          <p className="mt-1 text-sm text-stone-500">Every bride and planner enquiry, Hawaii and Oregon.</p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name, email or venue"
          className="w-72 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm placeholder:text-stone-400 focus:border-stone-400 focus:outline-none"
        />
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Segmented
          value={group}
          onChange={setGroup}
          options={GROUPS.map((g) => ({ key: g.key, label: `${g.label} ${rows ? counts[g.key] : ""}`.trim() }))}
        />
        <Segmented value={region} onChange={setRegion} options={[{ key: "", label: "All locations" }, { key: "HI", label: "Hawaii" }, { key: "OR", label: "Oregon" }]} />
        <Segmented value={type} onChange={setType} options={[{ key: "", label: "Brides & planners" }, { key: "bride", label: "Brides" }, { key: "planner", label: "Planners" }]} />
        <Segmented value={sort} onChange={setSort} options={[{ key: "received", label: "Newest first" }, { key: "wedding", label: "By wedding date" }]} />
      </div>

      <div className="soft-card mt-6 overflow-hidden rounded-xl border border-stone-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wider text-stone-500">
              <th className="px-4 py-3 font-medium">Client</th>
              <th className="px-4 py-3 font-medium">Location</th>
              <th className="px-4 py-3 font-medium">Wedding</th>
              <th className="px-4 py-3 font-medium">Venue</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 text-right font-medium">Received</th>
            </tr>
          </thead>
          <tbody>
            {rows === null && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-stone-400">Loading…</td>
              </tr>
            )}
            {rows !== null && shown.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-stone-400">No enquiries match.</td>
              </tr>
            )}
            {shown.map((e) => (
              <tr key={e.id} className="border-t border-stone-100 transition-colors hover:bg-stone-50">
                <td className="px-4 py-3">
                  <Link href={`/enquiries/${e.id}`} className="font-medium text-stone-900 hover:underline">
                    {e.client_name}
                  </Link>
                  <div className="text-xs text-stone-500">
                    {e.type === "planner" ? "Planner" : "Bride"} · {e.email}
                  </div>
                  {e.needs_review_flags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {e.needs_review_flags.map((f) => (
                        <span key={f} className="rounded-full border border-stone-300 px-2 py-px text-[10px] text-stone-600">
                          {FLAG_LABELS[f] ?? f}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-stone-700">{e.region ? REGION_NAMES[e.region] : <span className="text-stone-400">Unknown</span>}</td>
                <td className="px-4 py-3 text-stone-700">{formatDate(e.wedding_date)}</td>
                <td className="px-4 py-3 text-stone-600">{e.venue_name ?? <span className="text-stone-400">Not given</span>}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs ${
                      e.pipeline_status === "BOOKED"
                        ? "bg-stone-900 text-white"
                        : closedKeys.has(e.pipeline_status)
                          ? "bg-stone-100 text-stone-400"
                          : "border border-stone-300 text-stone-700"
                    }`}
                  >
                    {statusLabel(e.pipeline_status)}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-stone-500">{new Date(e.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
