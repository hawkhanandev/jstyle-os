"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/enquiries";
import { CONTRACT_STATUS, type Contract, docUrl } from "@/lib/paperwork";

export default function ContractsPage() {
  const [items, setItems] = useState<Contract[] | null>(null);
  useEffect(() => {
    api<Contract[]>("/contracts").then((cs) => setItems(cs.filter((c) => c.status !== "void"))).catch(() => setItems([]));
  }, []);
  return (
    <div>
      <h1 className="font-serif text-3xl text-stone-900">Contracts</h1>
      <p className="mt-1 text-stone-600">Mark a contract as signed from the client&apos;s Contract tab once it comes back.</p>
      {items?.length === 0 && <p className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-6 text-stone-500">No contracts yet.</p>}
      {items && items.length > 0 && (
        <table className="mt-6 w-full overflow-hidden rounded-lg border border-stone-200 bg-white text-sm">
          <thead className="bg-stone-50 text-left text-xs uppercase tracking-wide text-stone-500">
            <tr>
              <th className="px-4 py-2">Client</th>
              <th className="px-4 py-2">Wedding</th>
              <th className="px-4 py-2">Version</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Sent</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id} className="border-t border-stone-100">
                <td className="px-4 py-2">
                  <Link href={`/enquiries/${c.enquiry_id}`} className="hover:underline">
                    {c.client_name}
                  </Link>
                </td>
                <td className="px-4 py-2">{formatDate(c.wedding_date)}</td>
                <td className="px-4 py-2">
                  <a href={docUrl(c.document_id)} target="_blank" rel="noreferrer" className="text-rose-800 hover:underline">
                    v{c.version}
                  </a>
                </td>
                <td className="px-4 py-2">
                  <span className={`rounded px-2 py-0.5 ${CONTRACT_STATUS[c.status].tone}`}>{CONTRACT_STATUS[c.status].label}</span>
                </td>
                <td className="px-4 py-2">{c.sent_at ? new Date(c.sent_at).toLocaleDateString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
