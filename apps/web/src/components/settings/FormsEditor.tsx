"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Builtin, CustomQuestion, FieldOverride, FormLayout, LayoutEditor } from "@/lib/formLayout";

type Kind = "bride" | "planner";
const box = "w-full rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-sm focus:border-stone-900 focus:outline-none";
const TYPES: [CustomQuestion["type"], string][] = [
  ["text", "Short answer"],
  ["textarea", "Long answer"],
  ["select", "Dropdown"],
  ["yesno", "Yes / No"],
  ["number", "Number"],
];

const newId = () => `c_${Math.random().toString(36).slice(2, 10)}`;
const blankOverride: FieldOverride = { label: null, help: null, placeholder: null, hidden: false, required: false };

export function FormsEditor() {
  const [kind, setKind] = useState<Kind>("bride");
  const [ed, setEd] = useState<LayoutEditor | null>(null);
  const [layout, setLayout] = useState<FormLayout | null>(null);
  const [dirty, setDirty] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    setEd(null);
    setLayout(null);
    api<LayoutEditor>(`/form-layouts/${kind}`).then((r) => {
      setEd(r);
      setLayout(r.layout);
      setDirty(false);
    });
  }, [kind]);

  const update = (fn: (l: FormLayout) => FormLayout) => {
    setLayout((l) => (l ? fn(structuredClone(l)) : l));
    setDirty(true);
    setNote(null);
  };
  const setField = (name: string, patch: Partial<FieldOverride>) =>
    update((l) => ({ ...l, fields: { ...l.fields, [name]: { ...(l.fields[name] ?? blankOverride), ...patch } } }));
  const setCustom = (id: string, patch: Partial<CustomQuestion>) =>
    update((l) => ({ ...l, custom: l.custom.map((c) => (c.id === id ? { ...c, ...patch } : c)) }));
  const move = (name: string, dir: -1 | 1) =>
    update((l) => {
      const i = l.order.indexOf(name);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= l.order.length) return l;
      [l.order[i], l.order[j]] = [l.order[j], l.order[i]];
      return l;
    });
  const addQuestion = () =>
    update((l) => {
      const id = newId();
      return { ...l, custom: [...l.custom, { id, label: "New question", type: "text", options: [], required: false, help: null, wide: false }], order: [...l.order, id] };
    });
  const removeQuestion = (id: string) => update((l) => ({ ...l, custom: l.custom.filter((c) => c.id !== id), order: l.order.filter((n) => n !== id) }));

  async function save() {
    if (!layout) return;
    try {
      const r = await api<LayoutEditor>(`/form-layouts/${kind}`, { method: "PUT", body: JSON.stringify(layout) });
      setEd(r);
      setLayout(r.layout);
      setDirty(false);
      setNote("Saved. The public form shows the change straight away.");
    } catch (err) {
      setNote(err instanceof ApiError ? err.message : "Could not save.");
    }
  }
  async function reset() {
    if (!confirm(`Put the ${kind} form back to its original fields and wording? Custom questions are removed.`)) return;
    const r = await api<LayoutEditor>(`/form-layouts/${kind}/reset`, { method: "POST" });
    setEd(r);
    setLayout(r.layout);
    setDirty(false);
    setNote("Back to the original form.");
  }

  const builtin = new Map<string, Builtin>((ed?.builtins ?? []).map((b) => [b.name, b]));
  const custom = new Map<string, CustomQuestion>((layout?.custom ?? []).map((c) => [c.id, c]));

  return (
    <section id="forms" className="soft-card rounded-xl border border-stone-200">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-5 py-3">
        <div>
          <h2 className="font-medium text-stone-900">Enquiry forms</h2>
          <p className="text-xs text-stone-500">Wording, order and which questions are asked on the public forms.</p>
        </div>
        <div className="inline-flex rounded-lg border border-stone-200 p-0.5 text-sm">
          {(["bride", "planner"] as Kind[]).map((k) => (
            <button key={k} onClick={() => (!dirty || confirm("Discard unsaved changes?")) && setKind(k)} className={`rounded-md px-3 py-1 ${kind === k ? "bg-stone-900 text-white" : "text-stone-600"}`}>
              {k === "bride" ? "Bride form" : "Planner form"}
            </button>
          ))}
        </div>
      </div>

      {!layout && <div className="m-5 h-40 animate-pulse rounded-lg bg-stone-100" />}
      {layout && (
        <div className="space-y-5 px-5 py-4 text-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            <label>
              <span className="text-xs uppercase tracking-wider text-stone-500">Form title</span>
              <input className={box} value={layout.title} onChange={(e) => update((l) => ({ ...l, title: e.target.value }))} />
            </label>
            <label>
              <span className="text-xs uppercase tracking-wider text-stone-500">Button label</span>
              <input className={box} value={layout.submit_label} onChange={(e) => update((l) => ({ ...l, submit_label: e.target.value }))} />
            </label>
            <label className="sm:col-span-2">
              <span className="text-xs uppercase tracking-wider text-stone-500">Introduction (optional)</span>
              <textarea className={box} rows={2} value={layout.intro} onChange={(e) => update((l) => ({ ...l, intro: e.target.value }))} />
            </label>
          </div>

          <ol className="divide-y divide-stone-100 rounded-lg border border-stone-200">
            {layout.order.map((name, i) => {
              const b = builtin.get(name);
              const c = custom.get(name);
              const o = layout.fields[name] ?? blankOverride;
              return (
                <li key={name} className={`flex gap-3 px-3 py-3 ${b && o.hidden ? "bg-stone-50 opacity-60" : ""}`}>
                  <div className="flex flex-col">
                    <button aria-label="Move up" disabled={i === 0} onClick={() => move(name, -1)} className="px-1 text-stone-400 hover:text-stone-900 disabled:opacity-20">
                      ▲
                    </button>
                    <button aria-label="Move down" disabled={i === layout.order.length - 1} onClick={() => move(name, 1)} className="px-1 text-stone-400 hover:text-stone-900 disabled:opacity-20">
                      ▼
                    </button>
                  </div>
                  {b && (
                    <div className="grid flex-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
                      <div>
                        <input className={box} value={o.label ?? ""} placeholder={b.label} onChange={(e) => setField(name, { label: e.target.value || null })} />
                        <div className="mt-1 flex gap-1.5 text-[11px] text-stone-400">
                          <span>{b.label}</span>
                          {b.lock === "always" && <span className="rounded bg-stone-100 px-1.5 text-stone-600">always asked</span>}
                          {b.lock === "pricing" && <span className="rounded bg-stone-100 px-1.5 text-stone-600">used for pricing</span>}
                        </div>
                      </div>
                      <input className={box} value={o.help ?? ""} placeholder="Help text (optional)" onChange={(e) => setField(name, { help: e.target.value || null })} />
                      <div className="flex items-center gap-3 whitespace-nowrap text-xs text-stone-600">
                        <label className="flex items-center gap-1">
                          <input type="checkbox" checked={!o.hidden} disabled={!!b.lock} onChange={(e) => setField(name, { hidden: !e.target.checked, required: e.target.checked ? o.required : false })} />
                          Shown
                        </label>
                        <label className="flex items-center gap-1">
                          <input type="checkbox" checked={o.required} disabled={b.lock === "always" || o.hidden || b.type === "select"} onChange={(e) => setField(name, { required: e.target.checked })} />
                          Required
                        </label>
                      </div>
                    </div>
                  )}
                  {c && (
                    <div className="grid flex-1 gap-2 sm:grid-cols-[1fr_auto_auto]">
                      <div className="space-y-2">
                        <input className={box} value={c.label} onChange={(e) => setCustom(c.id, { label: e.target.value })} />
                        {c.type === "select" && (
                          <input
                            className={box}
                            placeholder="Choices, separated by commas"
                            defaultValue={c.options.join(", ")}
                            onBlur={(e) => setCustom(c.id, { options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                          />
                        )}
                        <input className={box} value={c.help ?? ""} placeholder="Help text (optional)" onChange={(e) => setCustom(c.id, { help: e.target.value || null })} />
                        <div className="text-[11px] text-stone-400">Your question · answers are added to the enquiry&apos;s notes</div>
                      </div>
                      <select className={`${box} h-fit`} value={c.type} onChange={(e) => setCustom(c.id, { type: e.target.value as CustomQuestion["type"] })}>
                        {TYPES.map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                      <div className="flex h-fit items-center gap-3 whitespace-nowrap pt-1.5 text-xs text-stone-600">
                        <label className="flex items-center gap-1">
                          <input type="checkbox" checked={c.required} onChange={(e) => setCustom(c.id, { required: e.target.checked })} />
                          Required
                        </label>
                        <button onClick={() => removeQuestion(c.id)} className="text-stone-500 hover:text-stone-900 hover:underline">
                          Remove
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ol>

          <div className="flex flex-wrap items-center gap-3">
            <button onClick={addQuestion} disabled={layout.custom.length >= 20} className="rounded-md border border-stone-300 px-3 py-1.5 hover:border-stone-900">
              + Add a question
            </button>
            <div className="flex-1" />
            <a href={`/forms/${kind}`} target="_blank" rel="noreferrer" className="text-stone-600 hover:underline">
              Open the public form
            </a>
            <button onClick={reset} className="text-stone-500 hover:underline">
              Reset to original
            </button>
            <button onClick={save} disabled={!dirty} className="rounded-md bg-stone-900 px-4 py-1.5 text-white disabled:opacity-40">
              Save form
            </button>
          </div>
          {note && <p className="rounded-md bg-stone-100 px-3 py-2 text-stone-800">{note}</p>}
        </div>
      )}
    </section>
  );
}
