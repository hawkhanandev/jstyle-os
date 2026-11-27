"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fmt, toCents, toDollars } from "@/lib/money";

type Rates = Record<string, number | null>;
type Card = {
  id: string;
  region: "HI" | "OR";
  version: number;
  effective_from: string;
  is_active: boolean;
  note: string | null;
  rates: Rates;
};

const FIELDS: { key: string; label: string; regions: ("HI" | "OR")[] }[] = [
  { key: "package_cents", label: "Bridal package", regions: ["HI", "OR"] },
  { key: "attendant_hair_cents", label: "Attendant hair (each)", regions: ["HI", "OR"] },
  { key: "attendant_makeup_cents", label: "Attendant makeup (each)", regions: ["HI", "OR"] },
  { key: "trial_cents", label: "Bridal trial", regions: ["HI", "OR"] },
  { key: "travel_per_stylist_cents", label: "Travel per stylist", regions: ["HI"] },
  { key: "travel_min_cents", label: "Travel fee minimum", regions: ["OR"] },
  { key: "travel_max_cents", label: "Travel fee maximum", regions: ["OR"] },
  { key: "minimum_total_cents", label: "Minimum booking", regions: ["OR"] },
  { key: "deposit_cents", label: "Deposit", regions: ["HI", "OR"] },
];
const NAMES = { HI: "Hawaii", OR: "Oregon" };

export function RateCards() {
  const [cards, setCards] = useState<Card[]>([]);
  const [editing, setEditing] = useState<Card | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  const load = () =>
    api<Card[]>("/rate-cards")
      .then(setCards)
      .catch(() => setCards([]));
  useEffect(() => {
    load();
  }, []);

  function startEdit(c: Card) {
    setEditing(c);
    setNote("");
    setError("");
    setDraft(
      Object.fromEntries(
        FIELDS.filter((f) => f.regions.includes(c.region)).map((f) => [f.key, toDollars(c.rates[f.key])]),
      ),
    );
  }

  async function save() {
    if (!editing) return;
    const body: Record<string, unknown> = { region: editing.region, note: note || null };
    for (const [k, v] of Object.entries(draft)) body[k] = v === "" ? null : toCents(v);
    try {
      await api("/rate-cards", { method: "POST", body: JSON.stringify(body) });
      setEditing(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    }
  }

  return (
    <section className="rounded-lg border border-stone-200 bg-white">
      <div className="border-b border-stone-200 px-5 py-3">
        <h2 className="font-medium text-stone-900">Rate cards</h2>
        <p className="text-sm text-stone-500">
          Saving creates a new version. Quotes already made keep the rates they were priced with.
        </p>
      </div>
      <div className="grid gap-6 p-5 md:grid-cols-2">
        {(["HI", "OR"] as const).map((region) => {
          const versions = cards.filter((c) => c.region === region);
          const active = versions.find((c) => c.is_active);
          return (
            <div key={region}>
              <div className="flex items-baseline justify-between">
                <h3 className="font-medium">{NAMES[region]}</h3>
                {active && (
                  <button onClick={() => startEdit(active)} className="text-sm text-rose-700 hover:underline">
                    Edit rates
                  </button>
                )}
              </div>
              {active ? (
                <table className="mt-2 w-full text-sm">
                  <tbody>
                    {FIELDS.filter((f) => f.regions.includes(region)).map((f) => (
                      <tr key={f.key} className="border-b border-stone-100">
                        <td className="py-1.5 text-stone-600">{f.label}</td>
                        <td className="py-1.5 text-right tabular-nums">{fmt(active.rates[f.key])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="mt-2 text-sm text-stone-500">No rate card yet.</p>
              )}
              <details className="mt-3 text-sm text-stone-500">
                <summary className="cursor-pointer">Version history ({versions.length})</summary>
                <ul className="mt-1 space-y-1">
                  {versions.map((v) => (
                    <li key={v.id}>
                      v{v.version} · {new Date(v.effective_from).toLocaleDateString()}
                      {v.is_active && " · active"}
                      {v.note && ` · ${v.note}`}
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          );
        })}
      </div>
      {editing && (
        <div className="border-t border-stone-200 bg-stone-50 p-5">
          <h3 className="font-medium">New {NAMES[editing.region]} version (in dollars)</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {FIELDS.filter((f) => f.regions.includes(editing.region)).map((f) => (
              <label key={f.key} className="text-sm">
                <span className="text-stone-600">{f.label}</span>
                <input
                  inputMode="decimal"
                  value={draft[f.key] ?? ""}
                  onChange={(e) => setDraft({ ...draft, [f.key]: e.target.value })}
                  className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5"
                />
              </label>
            ))}
            <label className="text-sm sm:col-span-2 lg:col-span-3">
              <span className="text-stone-600">Note (why the change)</span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5"
              />
            </label>
          </div>
          {error && <p className="mt-3 text-sm text-rose-700">{error}</p>}
          <div className="mt-4 flex gap-2">
            <button onClick={save} className="rounded-md bg-stone-900 px-4 py-1.5 text-sm text-white">
              Save as new version
            </button>
            <button onClick={() => setEditing(null)} className="rounded-md border border-stone-300 px-4 py-1.5 text-sm">
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
