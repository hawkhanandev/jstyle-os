"use client";

import { useCallback, useEffect, useState } from "react";
import { ReplyCard, type Suggestion } from "@/components/replies/ReplyCard";
import { api } from "@/lib/api";

export default function RepliesPage() {
  const [items, setItems] = useState<Suggestion[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(
    () =>
      api<Suggestion[]>("/replies")
        .then(setItems)
        .catch(() => setError("Could not load replies.")),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <h1 className="font-serif text-3xl text-stone-900">Replies to review</h1>
      <p className="mt-1 text-stone-600">
        Client replies to a quote, with a suggested meaning. Nothing changes until you confirm. You can correct the suggestion first.
      </p>
      {error && <p className="mt-3 rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      {items?.length === 0 && (
        <p className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-8 text-stone-500">No replies waiting.</p>
      )}
      <div className="mt-6 space-y-4">
        {items?.map((s) => (
          <ReplyCard key={s.id} s={s} onDone={load} />
        ))}
      </div>
    </div>
  );
}
