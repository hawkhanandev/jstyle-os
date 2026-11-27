"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type AllSettings = {
  business: { name: string; legal_name: string; address: string; email: string; phone: string };
  payment_instructions: { venmo: string; zelle: string };
  contract_terms: { bride: string; planner: string };
  scheduling: { deposit_due_days: number; balance_due_hours: number };
};

export function Business() {
  const [s, setS] = useState<AllSettings | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    api<AllSettings>("/settings").then(setS).catch(() => setMsg("Could not load settings."));
  }, []);

  async function save(path: string, body: unknown) {
    setMsg("");
    try {
      setS(await api<AllSettings>(`/settings/${path}`, { method: "PUT", body: JSON.stringify(body) }));
      setMsg("Saved.");
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Could not save.");
    }
  }

  if (!s) return <p className="text-stone-500">{msg || "Loading…"}</p>;
  return (
    <section className="rounded-lg border border-stone-200 bg-white">
      <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3">
        <h2 className="font-medium text-stone-900">Business details, payments and contract</h2>
        {msg && <span className="text-sm text-stone-500">{msg}</span>}
      </div>
      <div className="space-y-6 p-5 text-sm">
        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            const f = new FormData(ev.currentTarget);
            save("business", {
              name: f.get("name"),
              legal_name: f.get("legal_name"),
              address: f.get("address"),
              email: f.get("email") || null,
              phone: f.get("phone"),
            });
          }}
          className="grid gap-3 sm:grid-cols-2"
        >
          <Input name="name" label="Business name" value={s.business.name} />
          <Input name="legal_name" label="Legal name (on contracts and invoices)" value={s.business.legal_name} />
          <Input name="email" label="Email" value={s.business.email} />
          <Input name="phone" label="Phone" value={s.business.phone} />
          <label className="sm:col-span-2">
            <span className="text-stone-600">Address (one line per row)</span>
            <textarea name="address" rows={3} defaultValue={s.business.address} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
          </label>
          <Save />
        </form>

        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            const f = new FormData(ev.currentTarget);
            save("payment-instructions", { venmo: f.get("venmo"), zelle: f.get("zelle") });
          }}
          className="grid gap-3 border-t border-stone-100 pt-6 sm:grid-cols-2"
        >
          <Input name="venmo" label="Venmo handle" value={s.payment_instructions.venmo} />
          <Input name="zelle" label="Zelle email or phone" value={s.payment_instructions.zelle} />
          <Save />
        </form>

        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            const f = new FormData(ev.currentTarget);
            save("scheduling", { deposit_due_days: Number(f.get("deposit_due_days")), balance_due_hours: Number(f.get("balance_due_hours")) });
          }}
          className="grid gap-3 border-t border-stone-100 pt-6 sm:grid-cols-2"
        >
          <Input name="deposit_due_days" label="Deposit due (days after sending)" value={String(s.scheduling.deposit_due_days)} type="number" />
          <Input name="balance_due_hours" label="Balance due (hours before the wedding)" value={String(s.scheduling.balance_due_hours)} type="number" />
          <Save />
        </form>

        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            const f = new FormData(ev.currentTarget);
            save("contract-terms", { bride: f.get("bride"), planner: f.get("planner") });
          }}
          className="grid gap-3 border-t border-stone-100 pt-6"
        >
          <p className="text-stone-600">
            Contract terms, in simple HTML (&lt;p&gt;, &lt;ol&gt;, &lt;li&gt;, &lt;strong&gt;). Each new contract copies the terms as they are when it&apos;s prepared; contracts already prepared or sent don&apos;t change.
          </p>
          <label>
            <span className="text-stone-600">Bride contracts</span>
            <textarea name="bride" rows={10} defaultValue={s.contract_terms.bride} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5 font-mono text-xs" />
          </label>
          <label>
            <span className="text-stone-600">Planner contracts</span>
            <textarea name="planner" rows={10} defaultValue={s.contract_terms.planner} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5 font-mono text-xs" />
          </label>
          <Save />
        </form>
      </div>
    </section>
  );
}

function Input({ name, label, value, type = "text" }: { name: string; label: string; value: string; type?: string }) {
  return (
    <label>
      <span className="text-stone-600">{label}</span>
      <input name={name} type={type} defaultValue={value} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
    </label>
  );
}

function Save() {
  return (
    <div className="sm:col-span-2">
      <button className="rounded-md bg-stone-900 px-4 py-1.5 font-medium text-white hover:bg-stone-800">Save</button>
    </div>
  );
}
