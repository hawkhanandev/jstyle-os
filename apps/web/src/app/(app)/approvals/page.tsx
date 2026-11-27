"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate, REGION_NAMES } from "@/lib/enquiries";
import { QuoteCard } from "@/components/quotes/QuotesTab";
import type { Quote } from "@/lib/quotes";

export default function ApprovalsPage() {
  const [queue, setQueue] = useState<Quote[] | null>(null);
  const [failed, setFailed] = useState<Quote[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [waiting, broken] = await Promise.all([
      api<Quote[]>("/quotes?status=awaiting_approval"),
      api<Quote[]>("/quotes?status=send_failed"),
    ]);
    setQueue(waiting);
    setFailed(broken);
  }, []);
  useEffect(() => {
    load().catch(() => setError("Could not load approvals."));
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  return (
    <div>
      <h1 className="font-serif text-3xl text-stone-900">Approvals</h1>
      <p className="mt-1 text-stone-600">Every quote waits here until Jessica approves it. Approving sends the email exactly as previewed.</p>
      {error && <p className="mt-3 rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      {!queue && !error && <p className="mt-6 text-stone-500">Loading…</p>}
      {queue && queue.length === 0 && failed.length === 0 && (
        <p className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-8 text-stone-500">Nothing waiting for approval.</p>
      )}
      {[...failed, ...(queue ?? [])].map((q) => (
        <div key={q.id} className="mt-6">
          <div className="mb-2 text-sm">
            <Link href={`/enquiries/${q.enquiry_id}`} className="font-medium text-stone-900 hover:underline">
              {q.client_name}
            </Link>
            <span className="text-stone-500">
              {" "}
              · {formatDate(q.wedding_date ?? null)} · {q.region ? REGION_NAMES[q.region] : ""}
            </span>
          </div>
          <QuoteCard quote={q} run={run} reload={load} />
        </div>
      ))}
    </div>
  );
}
