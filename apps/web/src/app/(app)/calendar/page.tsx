"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type Ev = { type: "wedding" | "trial"; date: string | null; at: string | null; title: string; enquiry_id: string; status: string; detail: string | null; timezone: string | null };

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function CalendarPage() {
  const [month, setMonth] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [events, setEvents] = useState<Ev[]>([]);
  const days = useMemo(() => {
    const start = new Date(month);
    start.setDate(1 - ((start.getDay() + 6) % 7)); // Monday first
    return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  }, [month]);

  useEffect(() => {
    api<Ev[]>(`/calendar?start=${iso(days[0])}&end=${iso(days[41])}`).then(setEvents).catch(() => setEvents([]));
  }, [days]);

  const byDay = (d: Date) =>
    events.filter((e) => {
      if (e.date) return e.date === iso(d);
      if (!e.at) return false;
      const local = new Date(e.at).toLocaleDateString("en-CA", { timeZone: e.timezone ?? undefined });
      return local === iso(d);
    });

  const label = month.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-3xl text-stone-900">Calendar</h1>
        <div className="flex items-center gap-3 text-sm">
          <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} className="rounded-md border border-stone-300 px-2 py-1">
            ←
          </button>
          <span className="w-36 text-center font-medium">{label}</span>
          <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} className="rounded-md border border-stone-300 px-2 py-1">
            →
          </button>
        </div>
      </div>
      <p className="mt-1 text-sm text-stone-600">Weddings (accepted and booked) and trials. Google Calendar sync comes with the Google connection.</p>
      <div className="mt-4 grid grid-cols-7 overflow-hidden rounded-lg border border-stone-200 bg-stone-200 text-xs" style={{ gap: 1 }}>
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d} className="bg-stone-50 px-2 py-1 font-medium text-stone-500">
            {d}
          </div>
        ))}
        {days.map((d) => (
          <div key={d.toISOString()} className={`min-h-24 bg-white p-1.5 ${d.getMonth() !== month.getMonth() ? "opacity-40" : ""}`}>
            <div className="text-stone-500">{d.getDate()}</div>
            {byDay(d).map((e, i) => (
              <Link
                key={i}
                href={`/enquiries/${e.enquiry_id}`}
                className={`mt-1 block truncate rounded px-1 py-0.5 ${e.type === "wedding" ? (e.status === "booked" ? "bg-rose-100 text-rose-900" : "bg-amber-50 text-amber-900") : "bg-sky-50 text-sky-900"}`}
                title={e.detail ?? ""}
              >
                {e.type === "trial" && e.at ? new Date(e.at).toLocaleTimeString("en-US", { timeZone: e.timezone ?? undefined, hour: "numeric", minute: "2-digit" }) + " " : ""}
                {e.title}
              </Link>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
