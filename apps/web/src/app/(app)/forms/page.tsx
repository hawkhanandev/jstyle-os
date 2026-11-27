"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Stats = Record<string, number>;
type Submission = {
  id: string;
  form: string;
  email: string | null;
  payload: Record<string, unknown>;
  spam_score: number;
  spam_reasons: string[];
  fill_seconds: number | null;
  created_at: string;
};

const REASONS: Record<string, string> = {
  honeypot: "Filled the hidden bot field",
  missing_form_token: "Form token missing",
  too_fast: "Submitted in under 4 seconds",
  form_too_old: "Form open over 24 hours",
  disposable_email: "Throwaway email address",
  email_domain_not_found: "Email domain doesn't exist",
  phone_format: "Odd phone number",
  no_wedding_date: "No date",
  date_in_past: "Date in the past",
  date_over_3_years: "Date over 3 years away",
  region_unknown: "Location not recognised",
  too_many_links: "Several links in the message",
  spam_words: "Spam words",
};

export default function FormsPage() {
  const [stats, setStats] = useState<Stats>({});
  const [held, setHeld] = useState<Submission[]>([]);
  const [origin, setOrigin] = useState("");

  const load = () => {
    api<Stats>("/form-submissions/stats").then(setStats).catch(() => undefined);
    api<Submission[]>("/form-submissions?status=held").then(setHeld).catch(() => setHeld([]));
  };
  useEffect(() => {
    setOrigin(window.location.origin);
    load();
  }, []);

  async function decide(id: string, action: "approve" | "delete") {
    await api(`/form-submissions/${id}/${action}`, { method: "POST" });
    load();
  }

  const snippet = (kind: string) =>
    `<iframe id="jstyle-${kind}-form" src="${origin}/forms/${kind}" style="width:100%;border:0;min-height:900px" loading="lazy"></iframe>
<script>window.addEventListener("message",function(e){if(e.origin==="${origin}"&&e.data&&e.data.jstyleFormHeight){document.getElementById("jstyle-${kind}-form").style.height=e.data.jstyleFormHeight+"px"}});</script>`;

  return (
    <div className="max-w-5xl">
      <h1 className="font-serif text-2xl text-stone-900">Forms</h1>
      <p className="mt-1 text-stone-600">The bride and planner forms are the only way new enquiries arrive.</p>

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Tile label="Accepted today" value={(stats.accepted ?? 0) + (stats.approved ?? 0)} />
        <Tile label="Merged into existing" value={stats.merged ?? 0} />
        <Tile label="Held for review" value={stats.held_total ?? 0} warn={(stats.held_total ?? 0) > 0} />
        <Tile label="Rejected today" value={stats.rejected ?? 0} />
      </div>

      <section className="mt-8 rounded-lg border border-stone-200 bg-white">
        <div className="border-b border-stone-200 px-5 py-3">
          <h2 className="font-medium">Spam review</h2>
          <p className="text-sm text-stone-500">
            Held submissions got the normal thank-you but no enquiry or email. Approve a real one to create the enquiry and send the
            acknowledgement.
          </p>
        </div>
        {held.length === 0 && <p className="px-5 py-6 text-sm text-stone-500">Nothing waiting.</p>}
        <ul>
          {held.map((s) => (
            <li key={s.id} className="border-b border-stone-100 px-5 py-4 last:border-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="text-sm">
                  <div className="font-medium text-stone-900">
                    {String(s.payload.full_name ?? s.payload.company_name ?? "Unknown")} · {s.email}
                    <span className="ml-2 rounded bg-stone-100 px-1.5 text-xs capitalize text-stone-600">{s.form}</span>
                  </div>
                  <div className="text-stone-500">
                    {new Date(s.created_at).toLocaleString()} · score {s.spam_score}
                    {s.fill_seconds != null && ` · filled in ${Math.round(s.fill_seconds)}s`}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {s.spam_reasons.map((r) => (
                      <span key={r} className="rounded bg-amber-50 px-1.5 text-xs text-amber-900">
                        {REASONS[r] ?? r}
                      </span>
                    ))}
                  </div>
                  {typeof s.payload.notes === "string" && s.payload.notes && (
                    <p className="mt-2 max-w-2xl text-stone-700">“{s.payload.notes}”</p>
                  )}
                </div>
                <div className="flex gap-2 text-sm">
                  <button onClick={() => decide(s.id, "approve")} className="rounded-md bg-stone-900 px-3 py-1.5 text-white">
                    Approve
                  </button>
                  <button onClick={() => decide(s.id, "delete")} className="rounded-md border border-stone-300 px-3 py-1.5">
                    Delete
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-8 grid gap-6 md:grid-cols-2">
        {(["bride", "planner"] as const).map((kind) => (
          <div key={kind} className="rounded-lg border border-stone-200 bg-white p-5">
            <div className="flex items-baseline justify-between">
              <h2 className="font-medium capitalize">{kind} form</h2>
              <Link href={`/forms/${kind}`} target="_blank" className="text-sm text-rose-700 hover:underline">
                Open form ↗
              </Link>
            </div>
            <p className="mt-1 text-sm text-stone-500">Paste this into a Custom HTML block on the WordPress page.</p>
            <textarea readOnly value={snippet(kind)} rows={6} className="mt-3 w-full rounded-md border border-stone-200 bg-stone-50 p-2 font-mono text-xs" />
          </div>
        ))}
      </section>
    </div>
  );
}

function Tile({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={`rounded-lg border p-4 ${warn ? "border-amber-300 bg-amber-50" : "border-stone-200 bg-white"}`}>
      <div className="text-sm text-stone-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}
