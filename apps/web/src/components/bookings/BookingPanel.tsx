"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fmt } from "@/lib/money";

export type Booking = {
  id: string;
  status: "pending" | "booked" | "cancelled";
  quote_version: number | null;
  accepted_at: string;
  accepted_via: "reply" | "staff";
  total_cents: number;
  deposit_cents: number;
  balance_cents: number;
  stylists_required: number | null;
  checklist: { key: string; label: string; done: boolean }[];
};

export function BookingPanel({ enquiryId, stamp }: { enquiryId: string; stamp?: string }) {
  const [b, setB] = useState<Booking | null | undefined>(undefined);
  const [error, setError] = useState("");
  const load = useCallback(() => api<Booking | null>(`/enquiries/${enquiryId}/booking`).then(setB), [enquiryId]);
  useEffect(() => {
    load().catch(() => setB(null));
  }, [load, stamp]);

  async function setStylists(n: number) {
    setError("");
    try {
      setB(await api<Booking>(`/enquiries/${enquiryId}/booking`, { method: "PATCH", body: JSON.stringify({ stylists_required: n }) }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    }
  }

  if (!b) return null;
  return (
    <section className="rounded-lg border border-stone-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-medium">Booking</h2>
        <span className={`rounded px-2 py-0.5 text-sm ${b.status === "booked" ? "bg-emerald-100 text-emerald-900" : "bg-amber-50 text-amber-900"}`}>
          {b.status === "booked" ? "Booked" : b.status === "cancelled" ? "Cancelled" : "Not booked yet"}
        </span>
      </div>
      <p className="mt-1 text-xs text-stone-500">
        Quote v{b.quote_version} accepted {new Date(b.accepted_at).toLocaleDateString()} ({b.accepted_via === "reply" ? "by email" : "recorded by staff"}) ·{" "}
        {fmt(b.total_cents)} total, {fmt(b.deposit_cents)} deposit
      </p>
      <ul className="mt-3 space-y-1.5 text-sm">
        {b.checklist.map((i) => (
          <li key={i.key} className="flex items-center gap-2">
            <span className={i.done ? "text-emerald-700" : "text-stone-400"}>{i.done ? "✓" : "○"}</span>
            <span className={i.done ? "text-stone-700" : "text-stone-900"}>{i.label}</span>
            {i.key === "stylists_required" && (
              <input
                type="number"
                min={1}
                defaultValue={b.stylists_required ?? ""}
                onBlur={(ev) => {
                  const n = Number(ev.target.value);
                  if (n >= 1 && n !== b.stylists_required) setStylists(n);
                }}
                className="ml-auto w-16 rounded-md border border-stone-300 px-2 py-0.5"
              />
            )}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-stone-500">The enquiry moves to Booked by itself once every item is ticked.</p>
      {error && <p className="mt-2 text-sm text-rose-800">{error}</p>}
    </section>
  );
}
