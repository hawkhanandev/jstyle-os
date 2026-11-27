export type Contract = {
  id: string;
  enquiry_id: string;
  client_name: string | null;
  wedding_date: string | null;
  version: number;
  status: "prepared" | "sending" | "sent" | "signed" | "void";
  document_id: string;
  sent_at: string | null;
  signed_on: string | null;
  signed_method: string | null;
  signed_note: string | null;
  signed_evidence_id: string | null;
  created_at: string;
};

export type Invoice = {
  id: string;
  number: string;
  enquiry_id: string;
  client_name: string | null;
  kind: "deposit" | "balance" | "adjustment";
  amount_cents: number;
  due_on: string;
  status: "prepared" | "issued" | "paid" | "void";
  document_id: string;
  issued_at: string | null;
  created_at: string;
};

export type Paperwork = { contracts: Contract[]; invoices: Invoice[] };

export const CONTRACT_STATUS: Record<Contract["status"], { label: string; tone: string }> = {
  prepared: { label: "Ready to send", tone: "bg-amber-50 text-amber-900" },
  sending: { label: "Sending", tone: "bg-sky-50 text-sky-900" },
  sent: { label: "Waiting for signature", tone: "bg-sky-50 text-sky-900" },
  signed: { label: "Signed", tone: "bg-emerald-100 text-emerald-900" },
  void: { label: "Replaced", tone: "bg-stone-100 text-stone-500" },
};

export const INVOICE_STATUS: Record<Invoice["status"], { label: string; tone: string }> = {
  prepared: { label: "Not sent", tone: "bg-amber-50 text-amber-900" },
  issued: { label: "Sent, unpaid", tone: "bg-sky-50 text-sky-900" },
  paid: { label: "Paid", tone: "bg-emerald-100 text-emerald-900" },
  void: { label: "Void", tone: "bg-stone-100 text-stone-500" },
};

export const SIGNED_METHODS: [string, string][] = [
  ["pdf", "Signed PDF returned"],
  ["paper", "Signed on paper"],
  ["other", "Other"],
];

export const docUrl = (id: string) => `/api/documents/${id}`;
