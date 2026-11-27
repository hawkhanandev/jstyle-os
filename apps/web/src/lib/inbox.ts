export type ThreadSummary = {
  id: string;
  subject: string;
  unread: boolean;
  last_message_at: string | null;
  last_direction: "inbound" | "outbound" | null;
  snippet: string;
  enquiry_id: string | null;
  client_name: string | null;
  client_email: string | null;
  pipeline_status: string | null;
  replies_sending: number;
};

export type Message = {
  id: string;
  direction: "inbound" | "outbound";
  from_addr: string;
  to_addrs: string[];
  subject: string;
  body_html: string | null;
  body_text: string | null;
  sent_at: string;
  template_key: string | null;
};

export type Thread = ThreadSummary & { messages: Message[] };

export function when(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : d.toLocaleDateString([], { month: "short", day: "numeric" });
}
