"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { FLAG_LABELS } from "@/lib/enquiries";
import { fmt, toCents, toDollars } from "@/lib/money";
import { type CustomLine, type EmailPreview, type Quote, QUOTE_STATUS, quoteAction } from "@/lib/quotes";

const OPEN = ["draft", "awaiting_approval", "sending", "send_failed"];

export function QuotesTab({ enquiryId, region, onChange }: { enquiryId: string; region: string | null; onChange: () => void }) {
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => api<Quote[]>(`/enquiries/${enquiryId}/quotes`).then(setQuotes), [enquiryId]);
  useEffect(() => {
    load().catch(() => setError("Could not load quotes."));
  }, [load]);

  async function run(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await load();
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  if (!quotes) return <p className="mt-6 text-stone-500">{error || "Loading…"}</p>;
  const open = quotes.find((q) => OPEN.includes(q.status));
  const history = quotes.filter((q) => q !== open);

  return (
    <div className="mt-6 space-y-6">
      {error && <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      {open ? (
        <QuoteCard key={open.id} quote={open} run={run} reload={load} />
      ) : (
        <div className="rounded-lg border border-dashed border-stone-300 bg-white p-6">
          <p className="text-stone-600">
            {quotes.length === 0 ? "No quote yet." : "No open quote."} The draft starts from the services and travel on the Overview tab
            and is priced on the active rate card.
          </p>
          <button
            disabled={!region}
            onClick={() => run(() => api(`/enquiries/${enquiryId}/quotes`, { method: "POST", body: "{}" }))}
            className="mt-4 rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-40"
          >
            {quotes.some((q) => q.status === "sent") ? "Start a revised quote" : "Create quote draft"}
          </button>
          {!region && <p className="mt-2 text-sm text-amber-800">Set the region on the Overview tab first.</p>}
        </div>
      )}
      {history.length > 0 && (
        <section>
          <h2 className="font-medium">Earlier versions</h2>
          <ul className="mt-2 space-y-2">
            {history.map((q) => (
              <HistoryRow
                key={q.id}
                quote={q}
                onAccept={() => {
                  if (window.confirm(`Record that the client accepted version ${q.version} (${fmt(q.total_cents)})?`)) run(() => quoteAction(q.id, "accept"));
                }}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function HistoryRow({ quote: q, onAccept }: { quote: Quote; onAccept: () => void }) {
  const [openPreview, setOpenPreview] = useState(false);
  const s = QUOTE_STATUS[q.status];
  return (
    <li className="rounded-md border border-stone-200 bg-white px-4 py-2 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <b>Version {q.version}</b>
        <span className={`rounded px-2 py-0.5 ${s.tone}`}>{s.label}</span>
        <span className="tabular-nums">{fmt(q.total_cents)}</span>
        {q.sent_at && <span className="text-stone-500">Sent {new Date(q.sent_at).toLocaleString()}</span>}
        {q.withdrawn_reason && <span className="text-stone-500">· {q.withdrawn_reason}</span>}
        {q.status === "sent" && (
          <button onClick={onAccept} className="ml-auto rounded-md border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-emerald-900">
            Client accepted (phone or in person)
          </button>
        )}
        {q.email_subject && (
          <button onClick={() => setOpenPreview(!openPreview)} className={`${q.status === "sent" ? "" : "ml-auto "}text-rose-800 hover:underline`}>
            {openPreview ? "Hide email" : "Show email sent"}
          </button>
        )}
      </div>
      {openPreview && <EmailFrame quoteId={q.id} />}
    </li>
  );
}

export function QuoteCard({
  quote: q,
  run,
  reload,
  showApprove = true,
}: {
  quote: Quote;
  run: (fn: () => Promise<unknown>) => Promise<void>;
  reload: () => Promise<unknown>;
  showApprove?: boolean;
}) {
  const s = QUOTE_STATUS[q.status];
  const draft = q.status === "draft";
  const [acks, setAcks] = useState<string[]>(q.acknowledged_flags);
  const [note, setNote] = useState(q.note_to_client ?? "");
  const [showEmail, setShowEmail] = useState(q.status === "awaiting_approval");
  const ackable = q.review_flags.filter((f) => f !== "travel_unconfirmed");

  const patch = (fields: Record<string, unknown>) => run(() => api(`/quotes/${q.id}`, { method: "PATCH", body: JSON.stringify(fields) }));
  const ask = (label: string) => window.prompt(label) ?? null;

  return (
    <section className="rounded-lg border border-stone-200 bg-white p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-serif text-xl">Quote, version {q.version}</h2>
        <span className={`rounded px-2 py-0.5 text-sm ${s.tone}`}>{s.label}</span>
        <span className="text-sm text-stone-500">
          Rate card v{q.rate_card_version}
          {q.active_rate_card_version && q.active_rate_card_version !== q.rate_card_version && (
            <>
              {" "}
              · current rates are v{q.active_rate_card_version}
              {draft && (
                <button onClick={() => run(() => quoteAction(q.id, "reprice"))} className="ml-2 text-rose-800 hover:underline">
                  Reprice on v{q.active_rate_card_version}
                </button>
              )}
            </>
          )}
        </span>
      </div>
      {q.rejection_note && draft && (
        <p className="mt-3 rounded-md bg-amber-50 p-2 text-sm text-amber-900">Jessica sent this back: {q.rejection_note}</p>
      )}
      {q.send_error && <p className="mt-3 rounded-md bg-rose-50 p-2 text-sm text-rose-900">The email could not be sent: {q.send_error}</p>}

      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <div>
          {draft && <DraftInputs quote={q} patch={patch} />}
          <table className="mt-3 w-full text-sm">
            <tbody>
              {q.line_items.map((l, i) => (
                <tr key={i} className="border-b border-stone-100">
                  <td className="py-1.5">
                    {l.description}
                    {l.quantity > 1 && <span className="text-stone-500"> × {l.quantity}</span>}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{fmt(l.amount_cents)}</td>
                </tr>
              ))}
              <tr className="font-medium">
                <td className="pt-2">Total</td>
                <td className="pt-2 text-right tabular-nums">{fmt(q.total_cents)}</td>
              </tr>
              <tr className="text-stone-600">
                <td>Deposit to book</td>
                <td className="text-right tabular-nums">{fmt(q.deposit_cents)}</td>
              </tr>
              <tr className="text-stone-600">
                <td>Balance</td>
                <td className="text-right tabular-nums">{fmt(q.balance_cents)}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="text-sm">
          {draft ? (
            <label className="block">
              <span className="text-stone-600">Personal note in the email (optional)</span>
              <textarea
                value={note}
                onChange={(ev) => setNote(ev.target.value)}
                onBlur={() => note !== (q.note_to_client ?? "") && patch({ note_to_client: note || null })}
                rows={4}
                className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5"
              />
            </label>
          ) : (
            q.note_to_client && (
              <p className="text-stone-700">
                <span className="text-stone-500">Note: </span>
                {q.note_to_client}
              </p>
            )
          )}

          {q.review_flags.length > 0 && (
            <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3">
              <p className="font-medium text-amber-900">Check before sending</p>
              {q.review_flags.includes("travel_unconfirmed") && (
                <p className="mt-1 text-amber-900">⚠ Travel isn&apos;t confirmed. Set the travel zone and stylists or fee.</p>
              )}
              {ackable.map((f) => (
                <label key={f} className="mt-1 flex items-center gap-2 text-amber-900">
                  <input
                    type="checkbox"
                    disabled={!draft}
                    checked={acks.includes(f)}
                    onChange={(ev) => setAcks(ev.target.checked ? [...acks, f] : acks.filter((a) => a !== f))}
                  />
                  {FLAG_LABELS[f] ?? f}: checked
                </label>
              ))}
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {draft && (
              <Primary onClick={() => run(() => quoteAction(q.id, "submit", { acknowledged_flags: acks }))}>Send to Jessica for approval</Primary>
            )}
            {q.status === "awaiting_approval" && showApprove && (
              <>
                <Primary onClick={() => run(() => quoteAction(q.id, "approve"))}>Approve and send</Primary>
                <Secondary
                  onClick={() => {
                    const n = ask("What should change? (saved on the draft)");
                    if (n !== null) run(() => quoteAction(q.id, "reject", { note: n || null }));
                  }}
                >
                  Send back to draft
                </Secondary>
              </>
            )}
            {q.status === "send_failed" && <Primary onClick={() => run(() => quoteAction(q.id, "retry-send"))}>Retry sending</Primary>}
            {q.status === "sending" && (
              <Secondary onClick={() => reload()}>Refresh</Secondary>
            )}
            {["draft", "awaiting_approval", "send_failed"].includes(q.status) && (
              <Secondary
                onClick={() => {
                  const r = ask("Why withdraw this quote?");
                  if (r !== null) run(() => quoteAction(q.id, "withdraw", { note: r || null }));
                }}
              >
                Withdraw
              </Secondary>
            )}
            <Secondary onClick={() => setShowEmail(!showEmail)}>{showEmail ? "Hide email" : "Preview email"}</Secondary>
          </div>
        </div>
      </div>
      {showEmail && <EmailFrame quoteId={q.id} stamp={`${q.total_cents}-${q.note_to_client}-${q.status}`} />}
    </section>
  );
}

function DraftInputs({ quote: q, patch }: { quote: Quote; patch: (f: Record<string, unknown>) => Promise<void> }) {
  const i = q.inputs;
  const [desc, setDesc] = useState("");
  const [amount, setAmount] = useState("");
  const custom = i.custom_lines ?? [];

  return (
    <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
      <Sel
        label="Bridal service"
        value={i.bridal_package}
        options={[["full", "Hair and makeup"], ["hair_only", "Hair only"], ["makeup_only", "Makeup only"], ["none", "None"]]}
        onChange={(v) => patch({ bridal_package: v })}
      />
      <NumIn label="Attendants: hair" value={i.attendant_hair} onChange={(v) => patch({ attendant_hair: v })} />
      <NumIn label="Attendants: makeup" value={i.attendant_makeup} onChange={(v) => patch({ attendant_makeup: v })} />
      <Sel label="Bridal trial" value={i.trial ? "yes" : "no"} options={[["no", "No"], ["yes", "Yes"]]} onChange={(v) => patch({ trial: v === "yes" })} />
      <Sel
        label="Travel zone"
        value={i.travel_zone}
        options={[["unknown", "Not confirmed"], ["in_town", "In town / no fee"], ["outside", "Outside (travel fee)"], ["out_of_area", "Out of area"]]}
        onChange={(v) => patch({ travel_zone: v })}
      />
      <NumIn label="Stylists travelling" value={i.stylists_required ?? 0} onChange={(v) => patch({ stylists_required: v || null })} />
      <label>
        <span className="text-stone-600">Travel fee override ($)</span>
        <input
          inputMode="decimal"
          defaultValue={toDollars(i.travel_fee_cents)}
          onBlur={(ev) => {
            const cents = ev.target.value.trim() ? toCents(ev.target.value) : null;
            if (cents !== i.travel_fee_cents) patch({ travel_fee_cents: cents });
          }}
          className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5"
        />
      </label>
      <div className="col-span-2 sm:col-span-3">
        <span className="text-stone-600">Extra lines</span>
        {custom.map((c: CustomLine, n: number) => (
          <div key={n} className="mt-1 flex items-center gap-2">
            <span className="flex-1">{c.description}</span>
            <span className="tabular-nums">{fmt(c.amount_cents * c.quantity)}</span>
            <button onClick={() => patch({ custom_lines: custom.filter((_, k) => k !== n) })} className="text-rose-800 hover:underline">
              Remove
            </button>
          </div>
        ))}
        <div className="mt-1 flex gap-2">
          <input placeholder="Description" value={desc} onChange={(ev) => setDesc(ev.target.value)} className="flex-1 rounded-md border border-stone-300 px-2 py-1.5" />
          <input placeholder="$" inputMode="decimal" value={amount} onChange={(ev) => setAmount(ev.target.value)} className="w-24 rounded-md border border-stone-300 px-2 py-1.5" />
          <button
            disabled={!desc.trim() || !amount.trim()}
            onClick={() => {
              patch({ custom_lines: [...custom, { description: desc.trim(), amount_cents: toCents(amount), quantity: 1 }] });
              setDesc("");
              setAmount("");
            }}
            className="rounded-md border border-stone-300 px-3 disabled:opacity-40"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

export function EmailFrame({ quoteId, stamp }: { quoteId: string; stamp?: string }) {
  const [preview, setPreview] = useState<(EmailPreview & { frozen?: string }) | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<EmailPreview & { frozen?: string }>(`/quotes/${quoteId}/preview-email`)
      .then(setPreview)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not render the email."));
  }, [quoteId, stamp]);
  if (error) return <p className="mt-4 text-sm text-rose-800">{error}</p>;
  if (!preview) return <p className="mt-4 text-sm text-stone-500">Rendering…</p>;
  return (
    <div className="mt-4 rounded-md border border-stone-200">
      <div className="border-b border-stone-200 bg-stone-50 px-3 py-2 text-sm">
        <span className="text-stone-500">Subject: </span>
        {preview.subject}
        {preview.frozen === "true" && <span className="ml-2 text-xs text-stone-500">(exactly as approved)</span>}
      </div>
      <iframe title="Email preview" sandbox="" srcDoc={preview.html} className="h-[28rem] w-full rounded bg-snow" />
    </div>
  );
}

function Primary({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} className="rounded-md bg-stone-900 px-4 py-2 font-medium text-white hover:bg-stone-800">
      {children}
    </button>
  );
}

function Secondary({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} className="rounded-md border border-stone-300 bg-white px-3 py-2 hover:bg-stone-50">
      {children}
    </button>
  );
}

function Sel({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <label>
      <span className="text-stone-600">{label}</span>
      <select value={value} onChange={(ev) => onChange(ev.target.value)} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5">
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

function NumIn({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label>
      <span className="text-stone-600">{label}</span>
      <input
        type="number"
        min={0}
        defaultValue={value}
        onBlur={(ev) => Number(ev.target.value) !== value && onChange(Number(ev.target.value))}
        className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5"
      />
    </label>
  );
}
