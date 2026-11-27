import { api } from "@/lib/api";

export type QuoteLine = { kind: string; description: string; quantity: number; unit_cents: number; amount_cents: number };
export type CustomLine = { description: string; amount_cents: number; quantity: number };
export type QuoteInputs = {
  attendant_hair: number;
  attendant_makeup: number;
  trial: boolean;
  bridal_package: string;
  travel_zone: string;
  stylists_required: number | null;
  travel_fee_cents: number | null;
  custom_lines: CustomLine[];
};

export type Quote = {
  id: string;
  enquiry_id: string;
  version: number;
  status: "draft" | "awaiting_approval" | "sending" | "send_failed" | "sent" | "accepted" | "superseded" | "withdrawn";
  inputs: QuoteInputs;
  line_items: QuoteLine[];
  subtotal_cents: number;
  minimum_adjustment_cents: number;
  total_cents: number;
  deposit_cents: number;
  balance_cents: number;
  review_flags: string[];
  acknowledged_flags: string[];
  note_to_client: string | null;
  email_subject: string | null;
  rate_card_version: number | null;
  active_rate_card_version: number | null;
  submitted_at: string | null;
  approved_at: string | null;
  sent_at: string | null;
  send_error: string | null;
  rejection_note: string | null;
  withdrawn_reason: string | null;
  created_at: string;
  // Present on the approval queue only.
  client_name?: string;
  region?: "HI" | "OR" | null;
  wedding_date?: string | null;
};

export const QUOTE_STATUS: Record<Quote["status"], { label: string; tone: string }> = {
  draft: { label: "Draft", tone: "bg-stone-100 text-stone-800" },
  awaiting_approval: { label: "Waiting for Jessica", tone: "bg-amber-50 text-amber-900" },
  sending: { label: "Sending", tone: "bg-sky-50 text-sky-900" },
  send_failed: { label: "Send failed", tone: "bg-rose-100 text-rose-900" },
  sent: { label: "Sent", tone: "bg-emerald-50 text-emerald-900" },
  accepted: { label: "Accepted", tone: "bg-emerald-100 text-emerald-900" },
  superseded: { label: "Replaced by a revision", tone: "bg-stone-100 text-stone-500" },
  withdrawn: { label: "Withdrawn", tone: "bg-stone-100 text-stone-500" },
};

export type EmailPreview = { subject: string; html: string; text: string };

export const quoteAction = (id: string, action: string, body: unknown = {}) =>
  api<Quote>(`/quotes/${id}/${action}`, { method: "POST", body: JSON.stringify(body) });
