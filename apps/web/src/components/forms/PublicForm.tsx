"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";
import type { PublicField, PublicLayout } from "@/lib/formLayout";

type Kind = "bride" | "planner";
type Config = { form_token: string; turnstile_site_key: string; layout?: PublicLayout };

declare global {
  interface Window {
    turnstile?: { render: (el: HTMLElement, opts: Record<string, unknown>) => string };
  }
}

const input =
  "mt-1.5 w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 placeholder:text-stone-400 focus:border-stone-900 focus:outline-none focus:ring-1 focus:ring-stone-900";

const NUMBER_FIELDS = ["attendants_hair", "attendants_makeup", "people_count", "stylists_needed"];

export function PublicForm({ kind }: { kind: Kind }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [turnstileToken, setTurnstileToken] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const widget = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`/api/public/forms/config?kind=${kind}`)
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setConfig({ form_token: "", turnstile_site_key: "" }));
  }, [kind]);

  // Tell the parent WordPress page how tall we are, so the iframe has no scrollbar.
  useEffect(() => {
    const post = () => window.parent?.postMessage({ jstyleFormHeight: document.body.scrollHeight }, "*");
    post();
    const ro = new ResizeObserver(post);
    ro.observe(document.body);
    return () => ro.disconnect();
  }, []);

  function renderTurnstile() {
    if (!config?.turnstile_site_key || !widget.current || !window.turnstile) return;
    window.turnstile.render(widget.current, {
      sitekey: config.turnstile_site_key,
      callback: (t: string) => setTurnstileToken(t),
    });
  }
  useEffect(renderTurnstile, [config]);

  async function onSubmit(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const fd = new FormData(ev.currentTarget);
    const body: Record<string, unknown> = {};
    const custom: Record<string, string> = {};
    for (const [k, v] of fd.entries()) {
      if (k.startsWith("c_")) custom[k] = String(v);
      else body[k] = v;
    }
    for (const k of NUMBER_FIELDS) {
      if (k in body) body[k] = body[k] === "" ? (k.startsWith("attendants") ? 0 : null) : Number(body[k]);
    }
    if (kind === "bride") body.trial = fd.get("trial") === "yes";
    for (const [k, v] of Object.entries(body)) if (v === "" && k !== "website") body[k] = null;
    body.custom = custom;
    body.form_token = config?.form_token;
    body.turnstile_token = turnstileToken || null;
    setState("sending");
    try {
      const res = await fetch(`/api/public/enquiries/${kind}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setState("done");
        setMessage(data.message);
      } else {
        setState("error");
        setMessage(
          data.message ??
            (res.status === 422 ? "Please check the highlighted fields and try again." : "Something went wrong. Please try again."),
        );
      }
    } catch {
      setState("error");
      setMessage("We couldn't reach the server. Please try again.");
    }
  }

  if (state === "done") {
    return (
      <div className="mx-auto max-w-xl py-16 text-center">
        <h1 className="font-serif text-4xl text-stone-900">Thank you!</h1>
        <p className="mt-3 text-stone-600">{message}</p>
      </div>
    );
  }

  const layout = config?.layout;

  return (
    <form onSubmit={onSubmit} className="mx-auto grid max-w-2xl gap-5 sm:grid-cols-2">
      {config?.turnstile_site_key && <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" onLoad={renderTurnstile} />}
      <div className="sm:col-span-2">
        <h1 className="font-serif text-4xl text-stone-900">{layout?.title ?? (kind === "bride" ? "Bridal enquiry" : "Planner enquiry")}</h1>
        {layout?.intro && <p className="mt-2 whitespace-pre-line text-stone-600">{layout.intro}</p>}
      </div>

      {/* Honeypot: hidden from people, tempting to bots. */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
        <label>
          Website <input name="website" tabIndex={-1} autoComplete="off" />
        </label>
      </div>

      {!layout && <div className="h-64 animate-pulse rounded-lg bg-stone-100 sm:col-span-2" />}
      {layout?.fields.map((f) => <Field key={f.name} f={f} />)}

      <div ref={widget} className="sm:col-span-2" />
      {state === "error" && <p className="rounded-lg border border-stone-300 bg-stone-50 p-3 text-sm text-stone-900 sm:col-span-2">{message}</p>}
      <button
        disabled={state === "sending" || !config}
        className="rounded-lg bg-gradient-to-b from-stone-800 to-stone-900 px-6 py-3 font-medium tracking-wide text-white shadow-sm transition hover:from-stone-700 disabled:opacity-50 sm:col-span-2"
      >
        {state === "sending" ? "Sending…" : (layout?.submit_label ?? "Send enquiry")}
      </button>
    </form>
  );
}

function Field({ f }: { f: PublicField }) {
  const common = { name: f.name, required: f.required, className: input };
  let control: React.ReactNode;
  if (f.type === "select") {
    const first = f.options[0]?.value ?? "";
    control = (
      <select {...common} defaultValue={f.custom ? "" : first}>
        {f.custom && <option value="">Choose…</option>}
        {f.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  } else if (f.type === "textarea") {
    control = <textarea {...common} rows={4} placeholder={f.placeholder} />;
  } else if (f.type === "number") {
    const attendants = f.name.startsWith("attendants");
    control = <input {...common} type="number" min={0} max={attendants ? 30 : 100} defaultValue={attendants ? 0 : undefined} placeholder={f.placeholder} />;
  } else {
    control = <input {...common} type={f.type} minLength={f.name.endsWith("name") && f.required ? 2 : undefined} placeholder={f.placeholder} />;
  }
  return (
    <label className={`text-sm ${f.wide ? "sm:col-span-2" : ""}`}>
      <span className="font-medium text-stone-800">
        {f.label}
        {f.required && <span className="text-stone-400"> *</span>}
      </span>
      {control}
      {f.help && <span className="mt-1 block text-xs text-stone-500">{f.help}</span>}
    </label>
  );
}
