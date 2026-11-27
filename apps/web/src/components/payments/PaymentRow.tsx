"use client";

import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/enquiries";
import { fmt } from "@/lib/money";
import { METHODS, type Payment, PAYMENT_STATUS } from "@/lib/payments";

export function PaymentRow({ p, onChange, onError, showClient = false }: { p: Payment; onChange: () => void; onError: (m: string) => void; showClient?: boolean }) {
  async function act(action: string, ask?: string) {
    let reason: string | null = null;
    if (ask) {
      reason = window.prompt(ask);
      if (reason === null) return;
    }
    try {
      await api(`/payments/${p.id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) });
      onChange();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }
  const s = PAYMENT_STATUS[p.status];
  return (
    <tr className="border-t border-stone-100">
      {showClient && (
        <td className="px-4 py-2">
          <Link href={`/enquiries/${p.enquiry_id}`} className="hover:underline">
            {p.client_name}
          </Link>
        </td>
      )}
      <td className="px-4 py-2">{formatDate(p.received_on)}</td>
      <td className="px-4 py-2">
        {METHODS.find(([k]) => k === p.method)?.[1]}
        {p.reference && <span className="text-stone-500"> · {p.reference}</span>}
        {p.invoice_number && <span className="text-stone-500"> · {p.invoice_number}</span>}
      </td>
      <td className="px-4 py-2 text-right tabular-nums">{fmt(p.amount_cents)}</td>
      <td className="px-4 py-2">
        <span className={`rounded px-2 py-0.5 ${s.tone}`}>{s.label}</span>
        {p.status_reason && <span className="ml-2 text-xs text-stone-500">{p.status_reason}</span>}
      </td>
      <td className="space-x-3 px-4 py-2 text-right whitespace-nowrap">
        {p.status === "recorded" && (
          <>
            <button onClick={() => act("verify")} className="font-medium text-emerald-800 hover:underline">
              Verify
            </button>
            <button onClick={() => act("reject", "Why reject it? (e.g. not in Venmo)")} className="text-rose-800 hover:underline">
              Reject
            </button>
            <button onClick={() => act("void")} className="text-stone-500 hover:underline">
              Delete entry
            </button>
          </>
        )}
        {p.status === "verified" && (
          <button onClick={() => act("void", "Why void this verified payment?")} className="text-stone-500 hover:underline">
            Void
          </button>
        )}
        {p.status === "rejected" && (
          <button onClick={() => act("reopen")} className="text-stone-500 hover:underline">
            Reopen
          </button>
        )}
      </td>
    </tr>
  );
}
