"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/enquiries";
import { fmt } from "@/lib/money";
import { CONTRACT_STATUS, type Contract, docUrl, INVOICE_STATUS, type Paperwork, SIGNED_METHODS } from "@/lib/paperwork";

export function ContractTab({ enquiryId, pipelineStatus, onChange }: { enquiryId: string; pipelineStatus: string; onChange: () => void }) {
  const [p, setP] = useState<Paperwork | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api<Paperwork>(`/enquiries/${enquiryId}/paperwork`).then(setP), [enquiryId]);
  useEffect(() => {
    load().catch(() => setError("Could not load the paperwork."));
  }, [load]);
  useEffect(() => {
    if (!p?.contracts.some((c) => c.status === "sending")) return;
    const t = setTimeout(() => load().then(onChange), 2500);
    return () => clearTimeout(t);
  }, [p, load, onChange]);

  async function run(path: string, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError("");
    try {
      setP(await api<Paperwork>(`/enquiries/${enquiryId}/contract/${path}`, { method: "POST" }));
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (!p) return <p className="mt-6 text-stone-500">{error || "Loading…"}</p>;
  const current = p.contracts.find((c) => c.status !== "void");
  const deposit = p.invoices.find((i) => i.kind === "deposit" && i.status !== "void");
  const canPrepare = pipelineStatus === "QUOTE_ACCEPTED" && (!current || current.status === "prepared");

  if (!current && pipelineStatus !== "QUOTE_ACCEPTED") {
    return <p className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-6 text-stone-500">The contract is prepared once the client accepts a quote.</p>;
  }

  return (
    <div className="mt-6 space-y-6">
      {error && <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-serif text-xl">Contract{current ? `, version ${current.version}` : ""}</h2>
          {current && <span className={`rounded px-2 py-0.5 text-sm ${CONTRACT_STATUS[current.status].tone}`}>{CONTRACT_STATUS[current.status].label}</span>}
        </div>
        {!current && <p className="mt-2 text-sm text-stone-600">Generates the contract and the deposit invoice as PDFs from the accepted quote, so you can check them before sending.</p>}

        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          {current && (
            <a href={docUrl(current.document_id)} target="_blank" rel="noreferrer" className="rounded-md border border-stone-300 px-3 py-2 hover:bg-stone-50">
              Open contract PDF
            </a>
          )}
          {deposit && (
            <a href={docUrl(deposit.document_id)} target="_blank" rel="noreferrer" className="rounded-md border border-stone-300 px-3 py-2 hover:bg-stone-50">
              Open deposit invoice {deposit.number}
            </a>
          )}
          {canPrepare && (
            <button disabled={busy} onClick={() => run("prepare")} className="rounded-md border border-stone-300 px-3 py-2 hover:bg-stone-50 disabled:opacity-40">
              {current ? "Regenerate" : "Prepare contract and deposit invoice"}
            </button>
          )}
          {current?.status === "prepared" && (
            <button
              disabled={busy}
              onClick={() => run("send", "Send the contract and deposit invoice to the client in one email?")}
              className="rounded-md bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-800 disabled:opacity-40"
            >
              Send both to the client
            </button>
          )}
        </div>
        {deposit && (
          <p className="mt-3 text-sm text-stone-600">
            Deposit {fmt(deposit.amount_cents)} due {formatDate(deposit.due_on)} · <span className={`rounded px-1.5 ${INVOICE_STATUS[deposit.status].tone}`}>{INVOICE_STATUS[deposit.status].label}</span>
          </p>
        )}
        {current?.status === "sent" && <MarkSigned contract={current} onDone={() => load().then(onChange)} />}
        {current?.status === "signed" && (
          <p className="mt-4 rounded-md bg-emerald-50 p-3 text-sm text-emerald-900">
            Signed {formatDate(current.signed_on)} ({SIGNED_METHODS.find(([k]) => k === current.signed_method)?.[1] ?? current.signed_method})
            {current.signed_note && ` · ${current.signed_note}`}
            {current.signed_evidence_id && (
              <>
                {" · "}
                <a href={docUrl(current.signed_evidence_id)} target="_blank" rel="noreferrer" className="underline">
                  signed copy
                </a>
              </>
            )}
          </p>
        )}
      </section>

      {p.contracts.filter((c) => c !== current).length > 0 && (
        <section>
          <h3 className="text-sm font-medium text-stone-600">Earlier versions</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {p.contracts
              .filter((c) => c !== current)
              .map((c) => (
                <li key={c.id}>
                  <a href={docUrl(c.document_id)} target="_blank" rel="noreferrer" className="hover:underline">
                    Version {c.version}
                  </a>{" "}
                  · {CONTRACT_STATUS[c.status].label}
                </li>
              ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function MarkSigned({ contract, onDone }: { contract: Contract; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  async function submit(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    setError("");
    const form = new FormData(ev.currentTarget);
    const file = form.get("evidence");
    if (file instanceof File && !file.name) form.delete("evidence");
    try {
      await api(`/contracts/${contract.id}/mark-signed`, { method: "POST", body: form });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    }
  }
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="mt-4 rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800">
        Mark as signed
      </button>
    );
  }
  return (
    <form onSubmit={submit} className="mt-4 grid max-w-xl gap-3 rounded-md border border-stone-200 p-4 text-sm sm:grid-cols-2">
      <label>
        <span className="text-stone-600">Date signed</span>
        <input name="signed_on" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
      </label>
      <label>
        <span className="text-stone-600">How</span>
        <select name="method" className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5">
          {SIGNED_METHODS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label className="sm:col-span-2">
        <span className="text-stone-600">Signed copy (PDF or photo, optional)</span>
        <input name="evidence" type="file" accept="application/pdf,image/*" className="mt-1 block w-full" />
      </label>
      <label className="sm:col-span-2">
        <span className="text-stone-600">Note (optional)</span>
        <input name="note" className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
      </label>
      {error && <p className="text-rose-800 sm:col-span-2">{error}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button className="rounded-md bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-800">Save</button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-md border border-stone-300 px-3 py-2">
          Cancel
        </button>
      </div>
    </form>
  );
}
