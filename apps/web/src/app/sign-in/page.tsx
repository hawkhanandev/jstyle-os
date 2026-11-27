"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

const ERRORS: Record<string, string> = {
  not_allowed: "That Google account can't use Jstyle Business OS. Sign in with the business account.",
  expired: "The sign-in took too long or was interrupted. Please try again.",
};

function SignIn() {
  const params = useSearchParams();
  const error = params.get("error");
  const [devLogin, setDevLogin] = useState(false);
  useEffect(() => {
    fetch("/api/auth/config")
      .then((r) => r.json())
      .then((c) => setDevLogin(Boolean(c.dev_login)))
      .catch(() => undefined);
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-50">
      <div className="w-full max-w-sm rounded-xl border border-stone-200 bg-white p-8 text-center shadow-sm">
        <div className="font-serif text-3xl text-stone-900">Jstyle</div>
        <div className="text-xs uppercase tracking-widest text-stone-500">Business OS</div>
        {error && <p className="mt-6 rounded-md bg-rose-50 p-3 text-sm text-rose-900">{ERRORS[error] ?? "Sign-in failed."}</p>}
        <a
          href="/api/auth/google/start"
          className="mt-8 block rounded-md bg-stone-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-stone-800"
        >
          Sign in with Google
        </a>
        {devLogin && (
          <form method="post" action="/api/auth/dev-login" className="mt-3">
            <button className="w-full rounded-md border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 hover:bg-amber-100">
              Local sign-in (development only)
            </button>
          </form>
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
