"use client";

import Link from "next/link";
import { formatDate } from "@/lib/enquiries";
import { fmt } from "@/lib/money";
import { docUrl, type Invoice, INVOICE_STATUS } from "@/lib/paperwork";

export function InvoicesTable({ invoices, showClient = true }: { invoices: Invoice[]; showClient?: boolean }) {
  if (invoices.length === 0) return <p className="rounded-lg border border-dashed border-stone-300 bg-white p-6 text-stone-500">No invoices yet.</p>;
  return (
    <table className="w-full overflow-hidden rounded-lg border border-stone-200 bg-white text-sm">
      <thead className="bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
        <tr>
          <th className="px-4 py-2">Number</th>
          {showClient && <th className="px-4 py-2">Client</th>}
          <th className="px-4 py-2">Type</th>
          <th className="px-4 py-2 text-right">Amount</th>
          <th className="px-4 py-2">Due</th>
          <th className="px-4 py-2">Status</th>
        </tr>
      </thead>
      <tbody>
        {invoices.map((i) => (
          <tr key={i.id} className="border-t border-stone-100">
            <td className="px-4 py-2">
              <a href={docUrl(i.document_id)} target="_blank" rel="noreferrer" className="text-rose-800 hover:underline">
                {i.number}
              </a>
            </td>
            {showClient && (
              <td className="px-4 py-2">
                <Link href={`/enquiries/${i.enquiry_id}`} className="hover:underline">
                  {i.client_name}
                </Link>
              </td>
            )}
            <td className="px-4 py-2 capitalize">{i.kind}</td>
            <td className="px-4 py-2 text-right tabular-nums">{fmt(i.amount_cents)}</td>
            <td className="px-4 py-2">{formatDate(i.due_on)}</td>
            <td className="px-4 py-2">
              <span className={`rounded px-2 py-0.5 ${INVOICE_STATUS[i.status].tone}`}>{INVOICE_STATUS[i.status].label}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
