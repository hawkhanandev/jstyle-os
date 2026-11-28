"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Doc = { id: string; kind: string; filename: string; size_bytes: number; enquiry_id: string | null; client_name: string | null; created_at: string };

const KIND: Record<string, string> = {
  contract: "Contract",
  invoice: "Invoice",
  signed_contract: "Signed contract",
  prep_guide: "Preparation guide",
  final_timeline: "Final timeline",
};

export function DocumentsList({ enquiryId }: { enquiryId?: string }) {
  const [docs, setDocs] = useState<Doc[] | null>(null);
  useEffect(() => {
    api<Doc[]>(enquiryId ? `/documents?enquiry_id=${enquiryId}` : "/documents").then(setDocs).catch(() => setDocs([]));
  }, [enquiryId]);
  return (
    <>
      {docs?.length === 0 && <p className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-6 text-stone-500">No documents yet.</p>}
      {docs && docs.length > 0 && (
        <table className="mt-6 w-full overflow-hidden rounded-lg border border-stone-200 bg-white text-sm">
          <tbody>
            {docs.map((d) => (
              <tr key={d.id} className="border-t border-stone-100 first:border-0">
                <td className="px-4 py-2">
                  <a href={`/api/documents/${d.id}`} target="_blank" rel="noreferrer" className="text-rose-800 hover:underline">
                    {d.filename}
                  </a>
                </td>
                <td className="px-4 py-2 text-stone-600">{KIND[d.kind] ?? d.kind}</td>
                <td className="px-4 py-2">
                  {!enquiryId && d.enquiry_id && (
                    <Link href={`/enquiries/${d.enquiry_id}`} className="hover:underline">
                      {d.client_name}
                    </Link>
                  )}
                </td>
                <td className="px-4 py-2 text-right text-stone-500">{Math.max(1, Math.round(d.size_bytes / 1024))} KB</td>
                <td className="px-4 py-2 text-right text-stone-500">{new Date(d.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
