# User acceptance walk-through

For Jessica and Hanan, on a local copy (see [local-setup.md](local-setup.md)). Each journey says
what to do and what you should see. Tick it off, or write down what looked wrong.

Emails never leave your machine: every email the CRM sends lands in Mailpit at
http://localhost:8025. Two local-only helpers stand in for things that take days or need Gmail:

- **Pretend the client replied** (enquiry, Email tab) stands in for a client's email reply.
- **Send now (test)** (enquiry, scheduled emails list) sends a scheduled email immediately
  instead of waiting for its date.

Neither exists on the real server.

## Before you start

1. `docker compose up --build`, then open http://localhost:3000 and use **Local sign-in**.
2. In **Settings**, check the business details, Venmo and Zelle instructions, deposit and balance
   timing, contract wording and the preparation guide. The contract and guide wording ship as
   DRAFT: Jessica, replace them with your own text before going live.

## 1. A bride enquires

1. Open http://localhost:3000/forms/bride in a private window and submit a wedding in Hawaii.
   - [ ] An acknowledgement email appears in Mailpit.
   - [ ] The enquiry appears in **Pipeline** as New.
2. Submit the planner form (`/forms/planner`) for an Oregon wedding.
   - [ ] It appears too, marked as a planner enquiry.
3. Submit the bride form again, filling it in within two seconds.
   - [ ] Nothing is created; it waits in **Forms → Spam review**. Approve it and the enquiry and
     acknowledgement appear once.

## 2. Quote and approval

1. Open the Hawaii enquiry, **Quotes** tab, and draft a quote.
   - [ ] The prices match the rate card. Any flags (travel, short notice) must be ticked before
     you can submit.
2. Submit it, then approve it in **Approvals**.
   - [ ] The quote email in Mailpit is exactly the preview you approved.
   - [ ] The enquiry moves to Quote sent, and a follow-up email is scheduled five days later at
     10:00 local time.
3. Draft a revised quote and approve it.
   - [ ] Version 1 is shown as superseded but still readable.

## 3. The client replies

1. **Email** tab → **Pretend the client replied** with "Yes, we'd love to book!".
   - [ ] The reply shows unread in **Inbox**, and **Replies to review** suggests "Accept".
2. Confirm the suggestion.
   - [ ] The follow-up email is cancelled. The booking panel lists what's still missing: stylist
     count, signed contract and deposit.
3. Reply to the client from the Inbox.
   - [ ] The reply appears in Mailpit in the same conversation.

## 4. Contract and deposit

1. Set the number of stylists in the booking panel.
2. **Contract** tab → prepare, then send.
   - [ ] One email arrives with the contract PDF and the deposit invoice PDF (number JS-2026-0001
     or similar). The deposit equals the accepted quote's deposit.
3. **Mark as signed**, uploading any PDF as the signed copy.
   - [ ] The audit log in Settings records who marked it and when.
4. **Payments** tab → record a Venmo payment for the deposit, then verify it.
   - [ ] The enquiry becomes **Booked** and a booking confirmation email arrives.
   - [ ] The scheduled list now shows the preparation guide (14 days before), balance reminder
     (5 days before), final timeline (2 days before) and thank-you (2 days after).

## 5. Before the wedding

1. **Wedding ops** tab → add a trial with a date and time.
   - [ ] A trial reminder is scheduled two days before.
2. Use **Send now (test)** on the preparation guide.
   - [ ] Within a minute it arrives in Mailpit with the guide PDF.
3. Fill in the wedding-day plan and try **Send final timeline**.
   - [ ] It refuses while the balance is unpaid. Record and verify the balance; it then sends
     with the timeline PDF.
4. Change the wedding date on the enquiry.
   - [ ] Every scheduled email moves with it.
5. Check **Calendar** and **Dashboard**.
   - [ ] The wedding and trial show on the right days; the counts make sense.

## 6. Things going wrong

1. Record a payment and reject it.
   - [ ] It doesn't count towards the balance.
2. Void a verified deposit on a booked wedding.
   - [ ] The wedding stays booked and a task appears on the Dashboard asking you to follow up.
3. On another enquiry, **Cancel wedding** with a reason.
   - [ ] Its invoices and contract show as void and every scheduled email is cancelled.
4. A client who declines (**Pretend the client replied** with "We've decided to go with someone
   else", then confirm).
   - [ ] The enquiry closes as Lost and nothing more is sent.

## 7. Backups

1. Run `scripts/backup-local.sh`, then `scripts/restore-local.sh backups/<the new folder>`.
   - [ ] Everything you entered above is still there, and a contract PDF still downloads.

## Sign-off

| Who | Date | Notes |
| --- | --- | --- |
| Jessica | | |
| Hanan | | |
