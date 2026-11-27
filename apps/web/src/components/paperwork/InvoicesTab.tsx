"use client";

import { useEffect, useState } from "react";
import { InvoicesTable } from "@/components/paperwork/InvoicesTable";
import { api } from "@/lib/api";
import type { Paperwork } from "@/lib/paperwork";

export function InvoicesTab({ enquiryId }: { enquiryId: string }) {
  const [p, setP] = useState<Paperwork | null>(null);
  useEffect(() => {
    api<Paperwork>(`/enquiries/${enquiryId}/paperwork`).then(setP).catch(() => setP({ contracts: [], invoices: [] }));
  }, [enquiryId]);
  return <div className="mt-6">{p ? <InvoicesTable invoices={p.invoices} showClient={false} /> : <p className="text-stone-500">Loading…</p>}</div>;
}
