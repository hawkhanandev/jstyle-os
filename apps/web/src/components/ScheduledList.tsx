"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Scheduled = { id: string; kind: string; send_at: string; status: string; note: string | null };

const LABEL: Record<string, string> = {
  quote_follow_up: "Quote follow-up",
  balance_reminder: "Balance reminder",
  trial_reminder: "Trial reminder",
  prep_guide: "Preparation guide",
  final_timeline: "Final timeline",
  thank_you_review: "Thank-you and review request",
};

export function ScheduledList({ enquiryId, stamp }: { enquiryId: string; stamp?: string }) {
  const [rows, setRows] = useState<Scheduled[]>([]);
  useEffect(() => {
    api<Scheduled[]>(`/enquiries/${enquiryId}/scheduled-emails`).then(setRows).catch(() => setRows([]));
  }, [enquiryId, stamp]);
  if (rows.length === 0) return null;
  return (
    <section className="mt-6">
      <h2 className="text-sm font-medium text-stone-600">Scheduled emails</h2>
      <ul className="mt-2 space-y-1 text-sm">
        {rows.map((r) => (
          <li key={r.id} className="rounded-md border border-stone-200 bg-white px-4 py-2">
            <b>{LABEL[r.kind] ?? r.kind}</b> · {new Date(r.send_at).toLocaleString()} ·{" "}
            <span className={r.status === "scheduled" ? "text-sky-800" : "text-stone-500"}>{r.status}</span>
            {r.note && <span className="text-stone-500"> ({r.note})</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
