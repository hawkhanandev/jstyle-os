"use client";

import { useEffect, useState } from "react";
import { InvoicesTable } from "@/components/paperwork/InvoicesTable";
import { api } from "@/lib/api";
import type { Invoice } from "@/lib/paperwork";

export default function InvoicesPage() {
  const [items, setItems] = useState<Invoice[] | null>(null);
  useEffect(() => {
    api<Invoice[]>("/invoices").then(setItems).catch(() => setItems([]));
  }, []);
  return (
    <div>
      <h1 className="font-serif text-3xl text-stone-900">Invoices</h1>
      <p className="mt-1 text-stone-600">Numbered per year (JS-2026-0001). Click a number to open the PDF.</p>
      <div className="mt-6">{items ? <InvoicesTable invoices={items} /> : <p className="text-stone-500">Loading…</p>}</div>
    </div>
  );
}
