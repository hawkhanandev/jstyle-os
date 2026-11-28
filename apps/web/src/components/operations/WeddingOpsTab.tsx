"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fmt } from "@/lib/money";

type Row = { time: string; person: string; service: string; stylist: string };
type Trial = { id: string; starts_at: string; location: string | null; status: "scheduled" | "done" | "cancelled"; notes: string | null };
type Ops = {
  booking_status: string;
  timezone: string;
  outstanding_cents: number;
  plan: { getting_ready_address: string | null; timeline: Row[]; notes: string | null; final_timeline_sent_at: string | null };
  final_timeline_blockers: string[];
  trials: Trial[];
};

const EMPTY: Row = { time: "", person: "", service: "", stylist: "" };

// datetime-local value in the wedding's time zone <-> ISO with offset
function toLocalInput(iso: string, tz: string) {
  const d = new Date(iso);
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour") === "24" ? "00" : get("hour")}:${get("minute")}`;
}
function fromLocalInput(value: string, tz: string) {
  // Find the UTC instant whose wall-clock time in `tz` equals `value`.
  const guess = new Date(`${value}:00Z`);
  const shown = new Date(toLocalInput(guess.toISOString(), tz) + ":00Z");
  return new Date(guess.getTime() - (shown.getTime() - guess.getTime())).toISOString();
}
function showInTz(iso: string, tz: string) {
  return new Date(iso).toLocaleString("en-US", { timeZone: tz, weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function WeddingOpsTab({ enquiryId }: { enquiryId: string }) {
  const [ops, setOps] = useState<Ops | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [address, setAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [msg, setMsg] = useState("");
  const [missing, setMissing] = useState(false);

  const apply = (o: Ops) => {
    setOps(o);
    setRows(o.plan.timeline.length ? o.plan.timeline : [{ ...EMPTY }]);
    setAddress(o.plan.getting_ready_address ?? "");
    setNotes(o.plan.notes ?? "");
  };
  const load = useCallback(
    () =>
      api<Ops>(`/enquiries/${enquiryId}/operations`)
        .then(apply)
        .catch((err) => (err instanceof ApiError && err.status === 404 ? setMissing(true) : setMsg("Could not load."))),
    [enquiryId],
  );
  useEffect(() => {
    load();
  }, [load]);

  async function call(path: string, method: string, body?: unknown, ok = "Saved.") {
    setMsg("");
    try {
      apply(await api<Ops>(`/enquiries/${enquiryId}/${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) }));
      setMsg(ok);
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  if (missing) return <p className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-6 text-stone-500">Wedding operations open once the client accepts a quote.</p>;
  if (!ops) return <p className="mt-6 text-stone-500">{msg || "Loading…"}</p>;
  const tz = ops.timezone;
  const setRow = (i: number, k: keyof Row, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  return (
    <div className="mt-6 space-y-6 text-sm">
      {msg && <p className="rounded-md bg-stone-100 p-2 text-stone-700">{msg}</p>}

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h2 className="font-medium">Trials</h2>
        <p className="text-xs text-stone-500">Times are in the wedding&apos;s time zone ({tz}). A reminder email goes out 2 days before at 10am.</p>
        <ul className="mt-3 space-y-2">
          {ops.trials.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-3">
              <span className={t.status === "cancelled" ? "text-stone-400 line-through" : ""}>{showInTz(t.starts_at, tz)}</span>
              {t.location && <span className="text-stone-500">{t.location}</span>}
              <span className="text-stone-500">{t.status}</span>
              {t.status === "scheduled" && (
                <>
                  <button onClick={() => call(`trials/${t.id}`, "PUT", { ...t, status: "done" })} className="text-emerald-800 hover:underline">
                    Mark done
                  </button>
                  <button onClick={() => call(`trials/${t.id}`, "PUT", { ...t, status: "cancelled" })} className="text-stone-500 hover:underline">
                    Cancel
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            const f = new FormData(ev.currentTarget);
            call("trials", "POST", { starts_at: fromLocalInput(String(f.get("at")), tz), location: f.get("location") || null }, "Trial added.");
            ev.currentTarget.reset();
          }}
          className="mt-3 flex flex-wrap items-end gap-2"
        >
          <label>
            <span className="text-stone-600">Date and time</span>
            <input name="at" type="datetime-local" required className="mt-1 block rounded-md border border-stone-300 px-2 py-1.5" />
          </label>
          <label>
            <span className="text-stone-600">Where</span>
            <input name="location" className="mt-1 block rounded-md border border-stone-300 px-2 py-1.5" />
          </label>
          <button className="rounded-md border border-stone-300 px-3 py-1.5 hover:bg-stone-50">Add trial</button>
        </form>
      </section>

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h2 className="font-medium">Day-of plan</h2>
        <label className="mt-3 block">
          <span className="text-stone-600">Getting-ready address</span>
          <input value={address} onChange={(ev) => setAddress(ev.target.value)} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
        </label>
        <table className="mt-4 w-full">
          <thead className="text-left text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="pb-1">Time</th>
              <th className="pb-1">Who</th>
              <th className="pb-1">Service</th>
              <th className="pb-1">Stylist</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className="pr-2 pb-1">
                  <input type="time" value={r.time} onChange={(ev) => setRow(i, "time", ev.target.value)} className="rounded-md border border-stone-300 px-2 py-1" />
                </td>
                <td className="pr-2 pb-1">
                  <input value={r.person} onChange={(ev) => setRow(i, "person", ev.target.value)} placeholder="Bride" className="w-full rounded-md border border-stone-300 px-2 py-1" />
                </td>
                <td className="pr-2 pb-1">
                  <input value={r.service} onChange={(ev) => setRow(i, "service", ev.target.value)} placeholder="Hair and makeup" className="w-full rounded-md border border-stone-300 px-2 py-1" />
                </td>
                <td className="pr-2 pb-1">
                  <input value={r.stylist} onChange={(ev) => setRow(i, "stylist", ev.target.value)} className="w-full rounded-md border border-stone-300 px-2 py-1" />
                </td>
                <td className="pb-1">
                  <button onClick={() => setRows(rows.filter((_, j) => j !== i))} className="text-stone-400 hover:text-rose-800" aria-label="Remove row">
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={() => setRows([...rows, { ...EMPTY }])} className="mt-2 text-rose-800 hover:underline">
          + Add row
        </button>
        <label className="mt-3 block">
          <span className="text-stone-600">Notes for the client</span>
          <textarea value={notes} onChange={(ev) => setNotes(ev.target.value)} rows={2} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
        </label>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            onClick={() =>
              call("plan", "PUT", {
                getting_ready_address: address || null,
                timeline: rows.filter((r) => r.time && r.person),
                notes: notes || null,
              })
            }
            className="rounded-md bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-800"
          >
            Save plan
          </button>
          <button
            disabled={ops.final_timeline_blockers.length > 0}
            onClick={() => window.confirm("Send the final timeline PDF to the client now?") && call("final-timeline/send", "POST", undefined, "Final timeline queued.")}
            className="rounded-md border border-stone-300 px-4 py-2 hover:bg-stone-50 disabled:opacity-40"
          >
            Send final timeline
          </button>
          {ops.plan.final_timeline_sent_at && <span className="text-emerald-800">Sent {new Date(ops.plan.final_timeline_sent_at).toLocaleString()}</span>}
        </div>
        {ops.final_timeline_blockers.length > 0 && (
          <p className="mt-2 text-amber-800">
            The final timeline goes out only once the balance is paid ({fmt(ops.outstanding_cents)} still owed). Waiting on: {ops.final_timeline_blockers.join(", ").toLowerCase()}.
          </p>
        )}
      </section>
    </div>
  );
}
