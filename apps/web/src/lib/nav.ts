export type NavItem = { href: string; label: string; phase: number; summary: string };

// Every screen from the design doc. `phase` is when it becomes functional.
export const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Overview",
    items: [
      { href: "/", label: "Dashboard", phase: 1, summary: "Counts, upcoming weddings and trials, open tasks." },
      { href: "/enquiries", label: "Enquiries", phase: 2, summary: "Every enquiry in one list, by location and status." },
      { href: "/inbox", label: "Inbox", phase: 3, summary: "Conversations with brides and planners only." },
      { href: "/pipeline", label: "Pipeline", phase: 2, summary: "Every enquiry by commercial status." },
    ],
  },
  {
    section: "Sales",
    items: [
      { href: "/forms", label: "Forms", phase: 2, summary: "Bride and planner forms, spam review." },
      { href: "/approvals", label: "Approvals", phase: 3, summary: "Quotes waiting for Jessica's approval." },
      { href: "/replies", label: "Replies to review", phase: 4, summary: "Suggested intent on client replies." },
    ],
  },
  {
    section: "Bookings",
    items: [
      { href: "/contracts", label: "Contracts", phase: 5, summary: "Contract versions and Mark as signed." },
      { href: "/invoices", label: "Invoices", phase: 5, summary: "Deposit, balance and adjustment invoices." },
      { href: "/payments", label: "Payments", phase: 6, summary: "Record and verify Venmo and Zelle payments." },
      { href: "/documents", label: "Documents", phase: 7, summary: "Preparation guides and every other file." },
      { href: "/calendar", label: "Calendar", phase: 7, summary: "Weddings and trials." },
    ],
  },
  {
    section: "Admin",
    items: [{ href: "/settings", label: "Settings", phase: 1, summary: "Business details, rates, templates, sessions, audit log." }],
  },
];

export const ALL_ITEMS = NAV.flatMap((s) => s.items);
