"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { type EnquiryDetail, FLAG_LABELS, formatDate, REGION_NAMES, statusLabel } from "@/lib/enquiries";
import { fmt, toCents } from "@/lib/money";
import { QuotesTab } from "@/components/quotes/QuotesTab";
import { EmailTab } from "@/components/inbox/EmailTab";
import { BookingPanel } from "@/components/bookings/BookingPanel";
import { ContractTab } from "@/components/paperwork/ContractTab";
import { InvoicesTab } from "@/components/paperwork/InvoicesTab";
import { PaymentsTab } from "@/components/payments/PaymentsTab";
import { ScheduledList } from "@/components/ScheduledList";
import { DocumentsList } from "@/components/DocumentsList";
import { WeddingOpsTab } from "@/components/operations/WeddingOpsTab";

type Line = { kind: string; description: string; quantity: number; unit_cents: number; amount_cents: number };
type Price = {
  line_items: Line[];
  total_cents: number;
  deposit_cents: number;
  balance_cents: number;
  minimum_adjustment_cents: number;
  flags: string[];
};

const TABS = ["Overview", "Email", "Quotes", "Contract", "Invoices", "Payments", "Wedding ops", "Documents", "Activity"];

export default function EnquiryPage() {
  const { id } = useParams<{ id: string }>();
  const [e, setE] = useState<EnquiryDetail | null>(null);
  const [tab, setTab] = useState("Overview");
  const [error, setError] = useState("");
  const [price, setPrice] = useState<Price | null>(null);
  const [travelFee, setTravelFee] = useState("");

  const load = useCallback(() => api<EnquiryDetail>(`/enquiries/${id}`).then(setE), [id]);
  useEffect(() => {
    load().catch(() => setError("Enquiry not found."));
  }, [load]);

  useEffect(() => {
    if (!e?.region) return setPrice(null);
    const body = {
      region: e.region,
      attendant_hair: e.attendant_hair_count,
      attendant_makeup: e.attendant_makeup_count,
      trial: e.trial_requested,
      bridal_package: e.bridal_package ?? "full",
      travel_zone: e.travel_zone ?? "unknown",
      stylists_required: e.stylists_required,
      travel_fee_cents: travelFee ? toCents(travelFee) : null,
    };
    api<Price>("/pricing/preview", { method: "POST", body: JSON.stringify(body) })
      .then(setPrice)
      .catch(() => setPrice(null));
  }, [e, travelFee]);

  async function patch(fields: Record<string, unknown>) {
    setError("");
    try {
      await api(`/enquiries/${id}`, { method: "PATCH", body: JSON.stringify(fields) });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    }
  }

  async function act(action: string, askReason = false) {
    let reason: string | null = null;
    if (askReason) {
      reason = window.prompt("Reason (saved in the history)") ?? null;
      if (!reason) return;
    }
    setError("");
    try {
      await api(`/enquiries/${id}/${action}`, { method: "POST", body: JSON.stringify({ reason }) });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    }
  }

  async function cancelWedding() {
    const reason = window.prompt("Cancel this wedding? Every scheduled email stops and unpaid invoices are voided. Reason:");
    if (!reason) return;
    setError("");
    try {
      await api(`/enquiries/${id}/cancel-wedding`, { method: "POST", body: JSON.stringify({ reason }) });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel.");
    }
  }

  if (!e) return <p className="text-stone-500">{error || "Loading…"}</p>;
  const closed = ["LOST_DECLINED", "EXPIRED", "CANCELLED"].includes(e.pipeline_status);

  return (
    <div>
      <Link href="/pipeline" className="text-sm text-stone-500 hover:underline">
        ← Pipeline
      </Link>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl text-stone-900">{e.client_name}</h1>
          <p className="text-stone-600">
            {formatDate(e.wedding_date)} · {e.venue_name ?? "Venue not given"} · {e.region ? REGION_NAMES[e.region] : "Region unknown"}
            {e.type === "planner" && " · Planner enquiry"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="rounded-full bg-rose-50 px-3 py-1 font-medium text-rose-900">{statusLabel(e.pipeline_status)}</span>
          {e.pipeline_status === "NEW_INQUIRY" && <Btn onClick={() => act("start-review")}>Start review</Btn>}
          {["UNDER_REVIEW"].includes(e.pipeline_status) && <Btn onClick={() => act("request-info", true)}>Request info</Btn>}
          {e.pipeline_status === "NEEDS_INFORMATION" && <Btn onClick={() => act("reopen")}>Back to review</Btn>}
          {["QUOTE_SENT", "DISCUSSION_REVISION"].includes(e.pipeline_status) && <Btn onClick={() => act("mark-expired", true)}>Mark expired</Btn>}
          {["QUOTE_ACCEPTED", "CONTRACT_DEPOSIT_PENDING", "BOOKED"].includes(e.pipeline_status) ? (
            <Btn onClick={cancelWedding}>Cancel wedding</Btn>
          ) : (
            !closed && <Btn onClick={() => act("mark-lost", true)}>Mark lost</Btn>
          )}
          {closed && e.pipeline_status !== "CANCELLED" && <Btn onClick={() => act("reopen")}>Reopen</Btn>}
        </div>
      </div>
      {error && <p className="mt-3 rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>}
      {e.needs_review_flags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {e.needs_review_flags.map((f) => (
            <span key={f} className="rounded bg-amber-50 px-2 py-0.5 text-sm text-amber-900">
              {FLAG_LABELS[f] ?? f}
            </span>
          ))}
        </div>
      )}

      <div className="mt-6 flex gap-1 overflow-x-auto border-b border-stone-200 text-sm">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`whitespace-nowrap px-3 py-2 ${tab === t ? "border-b-2 border-rose-700 font-medium text-stone-900" : "text-stone-500"}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <section className="rounded-lg border border-stone-200 bg-white p-5 lg:col-span-2">
            <h2 className="font-medium">Details</h2>
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <Field label="Email" value={e.email} />
              <Field label="Phone" value={e.phone} />
              <Field label="Preferred contact" value={e.preferred_contact} />
              <Field label="Wedding type" value={e.wedding_type} />
              <Field label="Venue address" value={e.venue_address} />
              <Field label="Travel notes" value={e.travel_notes} />
              <Field label="Notes" value={e.notes} />
              <Field label="Received" value={new Date(e.created_at).toLocaleString()} />
            </dl>

            <h2 className="mt-6 font-medium">Services and travel</h2>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              <Select
                label="Region"
                value={e.region ?? ""}
                options={[["", "Unknown"], ["HI", "Hawaii"], ["OR", "Oregon"]]}
                onChange={(v) => patch({ region: v || null })}
              />
              <Select
                label="Bridal service"
                value={e.bridal_package ?? "full"}
                options={[["full", "Hair and makeup"], ["hair_only", "Hair only"], ["makeup_only", "Makeup only"], ["none", "None"]]}
                onChange={(v) => patch({ bridal_package: v })}
              />
              <Num label="Attendants: hair" value={e.attendant_hair_count} onChange={(v) => patch({ attendant_hair_count: v })} />
              <Num label="Attendants: makeup" value={e.attendant_makeup_count} onChange={(v) => patch({ attendant_makeup_count: v })} />
              <Select
                label="Bridal trial"
                value={e.trial_requested ? "yes" : "no"}
                options={[["no", "No"], ["yes", "Yes"]]}
                onChange={(v) => patch({ trial_requested: v === "yes" })}
              />
              <Select
                label="Travel zone"
                value={e.travel_zone ?? "unknown"}
                options={[["unknown", "Not confirmed"], ["in_town", e.region === "HI" ? "Town / Waikiki" : "No travel fee"], ["outside", "Outside (travel fee)"], ["out_of_area", "Out of area"]]}
                onChange={(v) => patch({ travel_zone: v })}
              />
              {e.region === "HI" && (
                <Num label="Stylists travelling" value={e.stylists_required ?? 0} onChange={(v) => patch({ stylists_required: v || null })} />
              )}
              {e.region === "OR" && (
                <label>
                  <span className="text-stone-600">Travel fee ($55–$100)</span>
                  <input
                    inputMode="decimal"
                    value={travelFee}
                    onChange={(ev) => setTravelFee(ev.target.value)}
                    className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5"
                  />
                </label>
              )}
            </div>
          </section>

          <div className="space-y-6">
          <BookingPanel enquiryId={e.id} stamp={e.pipeline_status} />
          <section className="rounded-lg border border-stone-200 bg-white p-5">
            <h2 className="font-medium">Price preview</h2>
            <p className="text-xs text-stone-500">From the active rate card. Create the quote on the Quotes tab.</p>
            {price ? (
              <>
                <table className="mt-3 w-full text-sm">
                  <tbody>
                    {price.line_items.map((l, i) => (
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
                      <td className="pt-2 text-right tabular-nums">{fmt(price.total_cents)}</td>
                    </tr>
                    <tr className="text-stone-600">
                      <td>Deposit</td>
                      <td className="text-right tabular-nums">{fmt(price.deposit_cents)}</td>
                    </tr>
                    <tr className="text-stone-600">
                      <td>Balance</td>
                      <td className="text-right tabular-nums">{fmt(price.balance_cents)}</td>
                    </tr>
                  </tbody>
                </table>
                {price.flags.length > 0 && (
                  <ul className="mt-3 space-y-1 text-sm text-amber-800">
                    {price.flags.map((f) => (
                      <li key={f}>⚠ {FLAG_LABELS[f] ?? f}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="mt-3 text-sm text-stone-500">Set the region to see a price.</p>
            )}
          </section>
          </div>
        </div>
      )}

      {tab === "Activity" && <ScheduledList enquiryId={e.id} stamp={e.pipeline_status} />}
      {tab === "Activity" && (
        <ul className="mt-6 space-y-2 text-sm">
          {e.history.length === 0 && <li className="text-stone-500">No status changes yet.</li>}
          {e.history.map((h, i) => (
            <li key={i} className="rounded-md border border-stone-200 bg-white px-4 py-2">
              <span className="text-stone-500">{new Date(h.at).toLocaleString()}</span> · {h.from_status ? statusLabel(h.from_status) : "Created"} →{" "}
              <b>{statusLabel(h.to_status)}</b>
              {h.reason && <span className="text-stone-600"> · {h.reason}</span>}
            </li>
          ))}
        </ul>
      )}

      {tab === "Email" && <EmailTab enquiryId={e.id} onChange={load} />}

      {tab === "Contract" && <ContractTab enquiryId={e.id} pipelineStatus={e.pipeline_status} onChange={load} />}
      {tab === "Invoices" && <InvoicesTab enquiryId={e.id} />}
      {tab === "Payments" && <PaymentsTab enquiryId={e.id} onChange={load} />}
      {tab === "Wedding ops" && <WeddingOpsTab enquiryId={e.id} />}
      {tab === "Documents" && <DocumentsList enquiryId={e.id} />}

      {tab === "Quotes" && <QuotesTab enquiryId={e.id} region={e.region} onChange={load} />}

      {!["Overview", "Email", "Quotes", "Contract", "Invoices", "Payments", "Wedding ops", "Documents", "Activity"].includes(tab) && (
        <div className="mt-6 rounded-lg border border-dashed border-stone-300 bg-white p-8 text-stone-500">
          {tab} arrives in a later phase.
        </div>
      )}
    </div>
  );
}

function Btn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} className="rounded-md border border-stone-300 bg-white px-3 py-1 hover:bg-stone-50">
      {children}
    </button>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-stone-500">{label}</dt>
      <dd className="text-stone-900">{value || "—"}</dd>
    </div>
  );
}

function Select({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
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

function Num({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
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
