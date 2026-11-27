"use client";

import { useCallback, useEffect, useState } from "react";
import { PaymentRow } from "@/components/payments/PaymentRow";
import { api, ApiError } from "@/lib/api";
import { fmt, toCents } from "@/lib/money";
import type { Paperwork } from "@/lib/paperwork";
import { METHODS, type Payment, type PaymentSummary } from "@/lib/payments";

type Data = { summary: PaymentSummary; payments: Payment[] };

export function PaymentsTab({ enquiryId, onChange }: { enquiryId: string; onChange: () => void }) {
  const [d, setD] = useState<Data | null>(null);
  const [invoices, setInvoices] = useState<Paperwork["invoices"]>([]);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);

  const load = useCallback(async () => {
    try {
      setD(await api<Data>(`/enquiries/${enquiryId}/payments`));
      setInvoices((await api<Paperwork>(`/enquiries/${enquiryId}/paperwork`)).invoices.filter((i) => i.status !== "void"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setMissing(true);
      else setError("Could not load payments.");
    }
  }, [enquiryId]);
  useEffect(() => {
    load();
  }, [load]);

  const refresh = () => {
    load();
    onChange();
  };

  async function submit(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    setError("");
    const f = new FormData(ev.currentTarget);
    const form = ev.currentTarget;
    try {
      await api(`/enquiries/${enquiryId}/payments`, {
        method: "POST",
        body: JSON.stringify({
          method: f.get("method"),
          amount_cents: toCents(String(f.get("amount"))),
          received_on: f.get("received_on"),
          invoice_id: f.get("invoice_id") || null,
          reference: f.get("reference") || null,
          note: f.get("note") || null,
          verify: f.get("verify") === "on",
        }),
      });
      form.reset();
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    }
  }

  if (missing) return <p className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-6 text-stone-500">Payments are recorded once the client accepts a quote.</p>;
  if (!d) return <p className="mt-6 text-stone-500">{error || "Loading…"}</p>;
  const s = d.summary;
  return (
    <div className="mt-6 space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Total" value={fmt(s.total_cents)} />
        <Tile label="Paid (verified)" value={fmt(s.paid_cents)} />
        <Tile label="Waiting to verify" value={fmt(s.awaiting_verification_cents)} />
        <Tile label="Still owed" value={fmt(s.outstanding_cents)} />
      </div>
      {error && <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}

      <form onSubmit={submit} className="grid gap-3 rounded-lg border border-stone-200 bg-white p-5 text-sm sm:grid-cols-3">
        <h2 className="font-medium sm:col-span-3">Record a payment</h2>
        <label>
          <span className="text-stone-600">Method</span>
          <select name="method" className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5">
            {METHODS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="text-stone-600">Amount ($)</span>
          <input name="amount" required inputMode="decimal" className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
        </label>
        <label>
          <span className="text-stone-600">Date received</span>
          <input name="received_on" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
        </label>
        <label>
          <span className="text-stone-600">For invoice</span>
          <select name="invoice_id" className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5">
            <option value="">Not linked</option>
            {invoices.map((i) => (
              <option key={i.id} value={i.id}>
                {i.number} · {i.kind} · {fmt(i.amount_cents)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="text-stone-600">Venmo/Zelle reference</span>
          <input name="reference" className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
        </label>
        <label>
          <span className="text-stone-600">Note</span>
          <input name="note" className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
        </label>
        <label className="flex items-center gap-2 sm:col-span-2">
          <input name="verify" type="checkbox" /> I can already see it in Venmo or Zelle (mark verified)
        </label>
        <div className="sm:text-right">
          <button className="rounded-md bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-800">Save payment</button>
        </div>
      </form>

      {d.payments.length > 0 && (
        <table className="w-full overflow-hidden rounded-lg border border-stone-200 bg-white text-sm">
          <tbody>
            {d.payments.map((p) => (
              <PaymentRow key={p.id} p={p} onChange={refresh} onError={setError} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-stone-500">{label}</div>
      <div className="mt-1 text-xl tabular-nums text-stone-900">{value}</div>
    </div>
  );
}
