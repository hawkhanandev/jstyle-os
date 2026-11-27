"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

const ERRORS: Record<string, string> = {
  not_allowed: "That Google account can't use Jstyle Business OS. Sign in with the business account.",
  expired: "The sign-in took too long or was interrupted. Please try again.",
  google_not_configured: "Google sign-in isn't set up on this computer yet. Use Local sign-in below.",
};

type AuthConfig = { dev_login: boolean; google: boolean };

function SignIn() {
  const params = useSearchParams();
  const error = params.get("error");
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [apiDown, setApiDown] = useState(false);
  useEffect(() => {
    fetch("/api/auth/config")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((c) => setConfig({ dev_login: Boolean(c.dev_login), google: Boolean(c.google) }))
      .catch(() => setApiDown(true));
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-50">
      <div className="w-full max-w-sm rounded-xl border border-stone-200 bg-white p-8 text-center shadow-sm">
        <div className="font-serif text-3xl text-stone-900">Jstyle</div>
        <div className="text-xs uppercase tracking-widest text-stone-500">Business OS</div>
        {error && <p className="mt-6 rounded-md bg-rose-50 p-3 text-sm text-rose-900">{ERRORS[error] ?? "Sign-in failed."}</p>}
        {apiDown && (
          <p className="mt-6 rounded-md bg-rose-50 p-3 text-left text-sm text-rose-900">
            The CRM server isn&apos;t responding. In the terminal run{" "}
            <code className="font-mono">docker compose logs api</code> to see why.
          </p>
        )}
        {config?.google && (
          <a
            href="/api/auth/google/start"
            className="mt-8 block rounded-md bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800"
          >
            Sign in with Google
          </a>
        )}
        {config?.dev_login && (
          <form method="post" action="/api/auth/dev-login" className={config.google ? "mt-3" : "mt-8"}>
            <button
              className={
                config.google
                  ? "w-full rounded-md border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 hover:bg-amber-100"
                  : "w-full rounded-md bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800"
              }
            >
              Local sign-in (this computer only)
            </button>
          </form>
        )}
        {config && !config.google && !config.dev_login && (
          <p className="mt-6 text-sm text-stone-600">Sign-in isn&apos;t configured yet.</p>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <SignIn />
    </Suspense>
  );
}
