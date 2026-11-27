# Acceptance checklist (PRD section 22, as amended)

| Criterion | Test | Status |
| --- | --- | --- |
| Hawaii and Oregon pricing formulas pass automated tests | `test_prd_hawaii_worked_example`, `test_prd_oregon_worked_example` | Done |
| Oregon minimum booking adjustment is displayed correctly | `test_oregon_minimum_adds_separate_line` | Done |
| Travel exceptions require staff confirmation | `test_hawaii_outside_without_stylist_count_is_blocked`, `test_unknown_travel_zone_is_flagged` | Done |
| Rate changes do not alter existing quotes | `test_snapshot_is_independent_of_later_rate_changes` (engine level; DB level in 2.2) | Partial |
| Hawaii overlapping weddings are supported / Oregon has no cap | No capacity check exists by design | Done |
| Both website forms create enquiries correctly | `test_clean_bride_creates_enquiry_and_ack`, `test_planner_form` | Done |
| Unrelated Gmail messages do not create enquiries | Only `create_enquiry` creates enquiries; it is called by the forms and Spam review only | Done (sync filter in Phase 3) |
| Held, honeypot, too-fast and rate-limited submissions never create an enquiry or acknowledgement | `test_suspicious_is_held_without_enquiry_or_email`, `test_too_fast_is_held`, `test_turnstile_failure_is_rejected`, `test_rate_limit_per_email` | Done |
| Approving a held submission creates exactly one enquiry and sends the acknowledgement | `test_spam_review_approve_and_delete` | Done (email sent once the worker lands in Phase 3) |
