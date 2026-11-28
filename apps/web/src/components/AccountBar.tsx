"use client";

import { useEffect, useState } from "react";
import { api, type Me } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

export function AccountBar() {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => {
        window.location.href = "/sign-in";
      });
  }, []);

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.href = "/sign-in";
  }

  return (
    <header className="flex items-center justify-end gap-4 border-b border-stone-200 bg-white/80 px-6 py-3 backdrop-blur text-sm">
      <ThemeToggle />
      {me && (
        <span className="text-stone-500">
          Business account · {me.device_label ?? "this device"}
        </span>
      )}
      <button onClick={signOut} className="rounded-md border border-stone-300 px-3 py-1 text-stone-700 hover:bg-stone-50">
        Sign out
      </button>
    </header>
  );
}
