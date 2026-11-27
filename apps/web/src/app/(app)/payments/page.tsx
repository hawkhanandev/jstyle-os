"use client";

import { useCallback, useEffect, useState } from "react";
import { PaymentRow } from "@/components/payments/PaymentRow";
import { api } from "@/lib/api";
import type { Payment } from "@/lib/payments";

export default function PaymentsPage() {
  const [toVerify, setToVerify] = useState<Payment[] | null>(null);
  const [recent, setRecent] = useState<Payment[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setToVerify(await api<Payment[]>("/payments?status=recorded"));
    setRecent((await api<Payment[]>("/payments")).filter((p) => p.status !== "recorded").slice(0, 50));
  }, []);
  useEffect(() => {
    load().catch(() => setError("Could not load payments."));
  }, [load]);

  return (
    <div>
      <h1 className="font-serif text-3xl text-stone-900">Payments</h1>
      <p className="mt-1 text-stone-600">Check each one in Venmo or Zelle before verifying. Only verified payments count towards deposits and balances.</p>
      {error && <p className="mt-3 rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      <h2 className="mt-6 font-medium">To verify</h2>
      {toVerify?.length === 0 && <p className="mt-2 text-sm text-stone-500">Nothing to verify.</p>}
      {toVerify && toVerify.length > 0 && <Table rows={toVerify} onChange={load} onError={setError} />}
      <h2 className="mt-8 font-medium">Recent</h2>
      {recent.length > 0 ? <Table rows={recent} onChange={load} onError={setError} /> : <p className="mt-2 text-sm text-stone-500">No payments yet.</p>}
    </div>
  );
}

function Table({ rows, onChange, onError }: { rows: Payment[]; onChange: () => void; onError: (m: string) => void }) {
  return (
    <table className="mt-2 w-full overflow-hidden rounded-lg border border-stone-200 bg-white text-sm">
      <tbody>
        {rows.map((p) => (
          <PaymentRow key={p.id} p={p} onChange={onChange} onError={onError} showClient />
        ))}
      </tbody>
    </table>
  );
}
