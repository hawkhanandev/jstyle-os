"use client";

import { useEffect, useState } from "react";
import { Automations } from "@/components/settings/Automations";
import { Business } from "@/components/settings/Business";
import { Devices } from "@/components/settings/Devices";
import { FormsEditor } from "@/components/settings/FormsEditor";
import { GoogleAccount } from "@/components/settings/GoogleAccount";
import { RateCards } from "@/components/settings/RateCards";
import { Templates } from "@/components/settings/Templates";

type Section = { key: string; label: string; hint: string; group: string; render: () => React.ReactNode };

const SECTIONS: Section[] = [
  { group: "Business", key: "business", label: "Business details", hint: "Name, legal name, address and contact details on contracts and invoices.", render: () => <Business part="details" /> },
  { group: "Business", key: "payments", label: "Payments & due dates", hint: "Venmo and Zelle details on invoices, and when deposits and balances are due.", render: () => <Business part="payments" /> },
  { group: "Business", key: "pricing", label: "Rates & pricing", hint: "Hawaii and Oregon rate cards used for every new quote.", render: () => <RateCards /> },
  { group: "Clients", key: "forms", label: "Enquiry forms", hint: "Questions on the bride and planner forms.", render: () => <FormsEditor /> },
  { group: "Clients", key: "emails", label: "Email templates", hint: "Wording of every email the CRM sends.", render: () => <Templates /> },
  { group: "Clients", key: "documents", label: "Contract & guide", hint: "Contract terms and the preparation guide sent before the wedding.", render: () => <Business part="documents" /> },
  { group: "System", key: "google", label: "Gmail & Calendar", hint: "The connected Google account for mail and calendar.", render: () => <GoogleAccount /> },
  { group: "System", key: "devices", label: "Signed-in devices", hint: "Where the business account is signed in.", render: () => <Devices /> },
  { group: "System", key: "activity", label: "Automation log", hint: "Emails and jobs the CRM ran, and any that failed.", render: () => <Automations /> },
];

const GROUPS = [...new Set(SECTIONS.map((s) => s.group))];

export default function SettingsPage() {
  const [key, setKey] = useState("business");

  useEffect(() => {
    const fromHash = () => {
      const h = window.location.hash.slice(1);
      if (SECTIONS.some((s) => s.key === h)) setKey(h);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

  const current = SECTIONS.find((s) => s.key === key) ?? SECTIONS[0];

  return (
    <div>
      <h1 className="font-serif text-3xl text-stone-900">Settings</h1>
      <div className="mt-6 grid gap-8 lg:grid-cols-[13rem_1fr]">
        <nav className="space-y-5 lg:sticky lg:top-6 lg:self-start">
          {GROUPS.map((g) => (
            <div key={g}>
              <div className="px-3 pb-1.5 text-[10px] font-medium uppercase tracking-[0.2em] text-stone-400">{g}</div>
              {SECTIONS.filter((s) => s.group === g).map((s) => (
                <a
                  key={s.key}
                  href={`#${s.key}`}
                  onClick={() => setKey(s.key)}
                  className={`block rounded-md px-3 py-1.5 text-sm transition-colors ${
                    s.key === current.key ? "bg-stone-900 text-white" : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                  }`}
                >
                  {s.label}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <div className="min-w-0">
          <div className="mb-4">
            <h2 className="text-lg font-medium text-stone-900">{current.label}</h2>
            <p className="text-sm text-stone-500">{current.hint}</p>
          </div>
          <div key={current.key}>{current.render()}</div>
        </div>
      </div>
    </div>
  );
}
