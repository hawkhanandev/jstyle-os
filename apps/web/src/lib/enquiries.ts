export type Enquiry = {
  id: string;
  type: "bride" | "planner";
  pipeline_status: string;
  closed_reason: string | null;
  region: "HI" | "OR" | null;
  timezone: string | null;
  client_name: string;
  email: string;
  phone: string | null;
  preferred_contact: string | null;
  wedding_date: string | null;
  venue_name: string | null;
  venue_address: string | null;
  wedding_type: string | null;
  bridal_package: string | null;
  attendant_hair_count: number;
  attendant_makeup_count: number;
  trial_requested: boolean;
  travel_zone: string | null;
  stylists_required: number | null;
  travel_notes: string | null;
  notes: string | null;
  needs_review_flags: string[];
  created_at: string;
};

export type EnquiryDetail = Enquiry & {
  history: { from_status: string | null; to_status: string; reason: string | null; at: string }[];
};

export const STAGES: { key: string; label: string }[] = [
  { key: "NEW_INQUIRY", label: "New" },
  { key: "UNDER_REVIEW", label: "Under review" },
  { key: "NEEDS_INFORMATION", label: "Needs info" },
  { key: "QUOTE_DRAFT", label: "Quote draft" },
  { key: "AWAITING_APPROVAL", label: "Awaiting approval" },
  { key: "QUOTE_SENT", label: "Quote sent" },
  { key: "DISCUSSION_REVISION", label: "Discussion" },
  { key: "QUOTE_ACCEPTED", label: "Accepted" },
  { key: "CONTRACT_DEPOSIT_PENDING", label: "Contract & deposit" },
  { key: "BOOKED", label: "Booked" },
];
export const CLOSED: { key: string; label: string }[] = [
  { key: "LOST_DECLINED", label: "Lost" },
  { key: "EXPIRED", label: "Expired" },
  { key: "CANCELLED", label: "Cancelled" },
];
export const statusLabel = (s: string) => [...STAGES, ...CLOSED].find((x) => x.key === s)?.label ?? s;

export const FLAG_LABELS: Record<string, string> = {
  region_unknown: "Region unknown",
  date_in_past: "Date in the past",
  date_under_14_days: "Wedding within 14 days",
  partial_bridal_package: "Partial bridal package",
  unusual_combination: "Unusual combination",
  travel_unconfirmed: "Travel not confirmed",
  travel_out_of_area: "Travel outside area",
};

export const REGION_NAMES = { HI: "Hawaii", OR: "Oregon" } as const;

export function formatDate(d: string | null) {
  if (!d) return "No date";
  return new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
