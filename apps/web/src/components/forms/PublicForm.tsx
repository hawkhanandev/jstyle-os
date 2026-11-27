"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type Kind = "bride" | "planner";
type Config = { form_token: string; turnstile_site_key: string };

declare global {
  interface Window {
    turnstile?: { render: (el: HTMLElement, opts: Record<string, unknown>) => string };
  }
}

const input = "mt-1 w-full rounded-md border border-stone-300 px-3 py-2 focus:border-rose-400 focus:outline-none";

export function PublicForm({ kind }: { kind: Kind }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [turnstileToken, setTurnstileToken] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const widget = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/public/forms/config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setConfig({ form_token: "", turnstile_site_key: "" }));
  }, []);

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
    const body: Record<string, unknown> = Object.fromEntries(fd.entries());
    for (const k of ["attendants_hair", "attendants_makeup", "people_count", "stylists_needed"]) {
      if (k in body) body[k] = body[k] === "" ? (k.startsWith("attendants") ? 0 : null) : Number(body[k]);
    }
    if (kind === "bride") body.trial = fd.get("trial") === "yes";
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
        <h1 className="font-serif text-3xl">Thank you!</h1>
        <p className="mt-3 text-stone-600">{message}</p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mx-auto grid max-w-2xl gap-4 sm:grid-cols-2">
      {config?.turnstile_site_key && (
        <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" onLoad={renderTurnstile} />
      )}
      <h1 className="font-serif text-3xl sm:col-span-2">{kind === "bride" ? "Bridal enquiry" : "Planner enquiry"}</h1>

      {/* Honeypot: hidden from people, tempting to bots. */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
        <label>
          Website <input name="website" tabIndex={-1} autoComplete="off" />
        </label>
      </div>

      {kind === "bride" ? (
        <>
          <L label="Full name" wide>
            <input name="full_name" required minLength={2} className={input} />
          </L>
          <L label="Email">
            <input name="email" type="email" required className={input} />
          </L>
          <L label="Phone">
            <input name="phone" type="tel" className={input} />
          </L>
          <L label="Wedding date">
            <input name="wedding_date" type="date" required className={input} />
          </L>
          <L label="Preferred contact">
            <select name="preferred_contact" className={input}>
              <option value="email">Email</option>
              <option value="phone">Phone call</option>
              <option value="text">Text</option>
            </select>
          </L>
        </>
      ) : (
        <>
          <L label="Company name">
            <input name="company_name" required minLength={2} className={input} />
          </L>
          <L label="Your name">
            <input name="contact_name" required minLength={2} className={input} />
          </L>
          <L label="Email">
            <input name="email" type="email" required className={input} />
          </L>
          <L label="Phone">
            <input name="phone" type="tel" className={input} />
          </L>
          <L label="Event date">
            <input name="event_date" type="date" required className={input} />
          </L>
          <L label="Bride or client name">
            <input name="client_name" className={input} />
          </L>
        </>
      )}

      <L label="Location">
        <select name="region" className={input} defaultValue="">
          <option value="">Choose…</option>
          <option value="HI">Hawaii</option>
          <option value="OR">Oregon</option>
        </select>
      </L>
      <L label="Venue name">
        <input name="venue_name" className={input} />
      </L>
      <L label="Venue address" wide>
        <input name="venue_address" className={input} />
      </L>

      {kind === "bride" ? (
        <>
          <L label="Bridal service">
            <select name="bridal_service" className={input}>
              <option value="full">Hair and makeup</option>
              <option value="hair_only">Hair only</option>
              <option value="makeup_only">Makeup only</option>
              <option value="none">None for the bride</option>
            </select>
          </L>
          <L label="Wedding type">
            <input name="wedding_type" placeholder="e.g. beach ceremony" className={input} />
          </L>
          <L label="Attendants needing hair">
            <input name="attendants_hair" type="number" min={0} max={30} defaultValue={0} className={input} />
          </L>
          <L label="Attendants needing makeup">
            <input name="attendants_makeup" type="number" min={0} max={30} defaultValue={0} className={input} />
          </L>
          <L label="Bridal trial">
            <select name="trial" className={input}>
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </L>
          <L label="Travel information">
            <input name="travel_notes" placeholder="Getting-ready location, timing" className={input} />
          </L>
        </>
      ) : (
        <>
          <L label="Number of people">
            <input name="people_count" type="number" min={0} className={input} />
          </L>
          <L label="Stylists needed">
            <input name="stylists_needed" type="number" min={0} className={input} />
          </L>
          <L label="Services needed" wide>
            <textarea name="services_needed" rows={3} className={input} />
          </L>
        </>
      )}

      <L label={kind === "bride" ? "Anything else?" : "Additional event information"} wide>
        <textarea name="notes" rows={4} className={input} />
      </L>

      <div ref={widget} className="sm:col-span-2" />
      {state === "error" && <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-900 sm:col-span-2">{message}</p>}
      <button
        disabled={state === "sending" || !config}
        className="rounded-md bg-stone-900 px-6 py-3 font-medium text-white disabled:opacity-50 sm:col-span-2"
      >
        {state === "sending" ? "Sending…" : "Send enquiry"}
      </button>
    </form>
  );
}

function L({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={`text-sm ${wide ? "sm:col-span-2" : ""}`}>
      <span className="text-stone-700">{label}</span>
      {children}
    </label>
  );
}
