"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Template = { id: string; key: string; version: number; name: string; subject: string; body: string; created_at: string };

export function Templates() {
  const [list, setList] = useState<Template[]>([]);
  const [open, setOpen] = useState<Template | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<{ subject: string; html: string } | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const load = () =>
    api<Template[]>("/templates")
      .then(setList)
      .catch(() => setList([]));
  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      api<{ subject: string; html: string }>("/templates/preview", { method: "POST", body: JSON.stringify({ subject, body }) })
        .then((p) => {
          setPreview(p);
          setError("");
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : "Preview failed."));
    }, 300);
    return () => clearTimeout(t);
  }, [open, subject, body]);

  function edit(t: Template) {
    setOpen(t);
    setSubject(t.subject);
    setBody(t.body);
    setSaved("");
  }

  async function save() {
    if (!open) return;
    try {
      const row = await api<Template>(`/templates/${open.key}/versions`, { method: "POST", body: JSON.stringify({ subject, body }) });
      setSaved(`Saved as version ${row.version}.`);
      setOpen(row);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    }
  }

  return (
    <section className="rounded-lg border border-stone-200 bg-white">
      <div className="border-b border-stone-200 px-5 py-3">
        <h2 className="font-medium text-stone-900">Email templates</h2>
        <p className="text-sm text-stone-500">
          First drafts written from the PRD. Saving keeps the old version. Variables look like {"{{ client_first_name }}"}.
        </p>
      </div>
      <div className="grid md:grid-cols-[220px_1fr]">
        <ul className="border-b border-stone-100 md:border-b-0 md:border-r">
          {list.map((t) => (
            <li key={t.key}>
              <button
                onClick={() => edit(t)}
                className={`w-full px-5 py-2 text-left text-sm ${open?.key === t.key ? "bg-rose-50 text-rose-900" : "hover:bg-stone-50"}`}
              >
                {t.name}
                <span className="ml-1 text-xs text-stone-400">v{t.version}</span>
              </button>
            </li>
          ))}
        </ul>
        {open ? (
          <div className="grid gap-4 p-5 xl:grid-cols-2">
            <div className="space-y-3 text-sm">
              <label className="block">
                <span className="text-stone-600">Subject</span>
                <input value={subject} onChange={(e) => setSubject(e.target.value)} className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5" />
              </label>
              <label className="block">
                <span className="text-stone-600">Body (HTML)</span>
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={16}
                  className="mt-1 w-full rounded-md border border-stone-300 px-2 py-1.5 font-mono text-xs"
                />
              </label>
              {error && <p className="text-rose-700">{error}</p>}
              {saved && <p className="text-emerald-700">{saved}</p>}
              <button onClick={save} className="rounded-md bg-stone-900 px-4 py-1.5 text-white">
                Save new version
              </button>
            </div>
            <div className="text-sm">
              <div className="text-stone-600">Preview with sample data</div>
              <div className="mt-1 rounded-md border border-stone-200">
                <div className="border-b border-stone-100 px-3 py-2 font-medium">{preview?.subject}</div>
                <iframe sandbox="" srcDoc={preview?.html ?? ""} className="h-96 w-full" title="Email preview" />
              </div>
            </div>
          </div>
        ) : (
          <p className="p-5 text-sm text-stone-500">Choose a template to edit.</p>
        )}
      </div>
    </section>
  );
}
