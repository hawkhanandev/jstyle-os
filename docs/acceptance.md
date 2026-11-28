# Acceptance checklist (PRD section 22, as amended)

| Criterion | Test | Status |
| --- | --- | --- |
| Hawaii and Oregon pricing formulas pass automated tests | `test_prd_hawaii_worked_example`, `test_prd_oregon_worked_example` | Done |
| Oregon minimum booking adjustment is displayed correctly | `test_oregon_minimum_adds_separate_line` | Done |
| Travel exceptions require staff confirmation | `test_hawaii_outside_without_stylist_count_is_blocked`, `test_unknown_travel_zone_is_flagged` | Done |
| Rate changes do not alter existing quotes | `test_snapshot_is_independent_of_later_rate_changes`, `test_rate_change_does_not_touch_existing_quote` | Done |
| Hawaii overlapping weddings are supported / Oregon has no cap | No capacity check exists by design | Done |
| Both website forms create enquiries correctly | `test_clean_bride_creates_enquiry_and_ack`, `test_planner_form` | Done |
| Unrelated Gmail messages do not create enquiries | Only `create_enquiry` creates enquiries; it is called by the forms and Spam review only | Done (sync filter in Phase 3) |
| Held, honeypot, too-fast and rate-limited submissions never create an enquiry or acknowledgement | `test_suspicious_is_held_without_enquiry_or_email`, `test_too_fast_is_held`, `test_turnstile_failure_is_rejected`, `test_rate_limit_per_email` | Done |
| Approving a held submission creates exactly one enquiry and sends the acknowledgement | `test_spam_review_approve_and_delete` | Done (email sent once the worker lands in Phase 3) |
| Jessica approves every quote before it is sent; the email sent is exactly the one previewed | `test_cannot_approve_without_submit`, `test_preview_is_frozen_after_approval`, `test_flags_must_be_acknowledged` | Done |
| A revised quote supersedes the earlier one and keeps its history | `test_revision_supersedes_and_keeps_v1` | Done |
| A failed quote email doesn't advance the pipeline and can be retried | `test_failed_send_leaves_pipeline_and_can_retry` | Done |
| A client's acceptance changes nothing until staff confirm it | `test_acceptance_needs_a_staff_click` | Done |
| Reply suggestions can be corrected or ignored | `test_staff_can_correct_the_suggestion`, `tests/unit/test_classify.py` | Done |
| A declining client closes the enquiry and any open revision | `test_decline_closes_and_withdraws_open_revision` | Done |
| The booking gate lists what's missing (contract, deposit, stylists) | `test_acceptance_needs_a_staff_click`, `test_staff_acceptance_and_stylists` | Done (contract in Phase 5, deposit in Phase 6) |
| Contract and deposit invoice arrive in one email; the invoice equals the accepted quote's deposit | `test_full_contract_flow_to_booked` | Done |
| Marking a contract signed is audited, stores the evidence and re-runs the gate | `test_full_contract_flow_to_booked` | Done |
| Invoice numbers are yearly and never repeat | `test_invoice_numbers_are_yearly_and_sequential` | Done |
| A failed contract email leaves the pipeline unchanged | `test_failed_send_returns_contract_to_prepared` | Done |
| BOOKED only with a signed contract and a verified deposit | `test_booked_only_with_signed_contract_and_verified_deposit` | Done |
| Payments count only once verified; voiding after booking raises a task instead of un-booking | `test_partial_and_rejected_payments` | Done |
| Scheduled emails go out at the right local time and are re-checked when due | `test_follow_up_is_sent_at_10am_local_five_days_later`, `test_follow_up_skipped_when_client_replied`, `test_local_time_conversion` | Done |
| Cancelling a wedding stops every pending email | `test_cancel_wedding_stops_everything` | Done |
| Overdue deposits raise a task | `test_overdue_deposit_raises_one_task` | Done |
| A booking runs from BOOKED to completed with every email at the right local time | `test_booking_schedules_every_wedding_email`, `test_last_minute_booking_sends_prep_guide_now`, `test_trial_reminder_two_days_before` | Done |
| The final timeline is only sent once the balance is paid in full | `test_final_timeline_waits_for_full_payment` | Done |
| Moving the wedding date moves every scheduled email | `test_booking_schedules_every_wedding_email` | Done |
