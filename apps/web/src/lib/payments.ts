export type Payment = {
  id: string;
  enquiry_id: string;
  client_name: string | null;
  invoice_id: string | null;
  invoice_number: string | null;
  method: "venmo" | "zelle" | "cash" | "check" | "other";
  amount_cents: number;
  received_on: string;
  reference: string | null;
  note: string | null;
  status: "recorded" | "verified" | "rejected" | "void";
  status_reason: string | null;
  verified_at: string | null;
};

export type PaymentSummary = { total_cents: number; paid_cents: number; awaiting_verification_cents: number; outstanding_cents: number };

export const METHODS: [Payment["method"], string][] = [
  ["venmo", "Venmo"],
  ["zelle", "Zelle"],
  ["cash", "Cash"],
  ["check", "Check"],
  ["other", "Other"],
];

export const PAYMENT_STATUS: Record<Payment["status"], { label: string; tone: string }> = {
  recorded: { label: "To verify", tone: "bg-amber-50 text-amber-900" },
  verified: { label: "Verified", tone: "bg-emerald-100 text-emerald-900" },
  rejected: { label: "Rejected", tone: "bg-rose-50 text-rose-900" },
  void: { label: "Void", tone: "bg-stone-100 text-stone-500" },
};
