# Acceptance checklist (PRD section 22, as amended)

| Criterion | Test | Status |
| --- | --- | --- |
| Hawaii and Oregon pricing formulas pass automated tests | `test_prd_hawaii_worked_example`, `test_prd_oregon_worked_example` | Done |
| Oregon minimum booking adjustment is displayed correctly | `test_oregon_minimum_adds_separate_line` | Done |
| Travel exceptions require staff confirmation | `test_hawaii_outside_without_stylist_count_is_blocked`, `test_unknown_travel_zone_is_flagged` | Done |
| Rate changes do not alter existing quotes | `test_snapshot_is_independent_of_later_rate_changes` (engine level; DB level in 2.2) | Partial |
| Hawaii overlapping weddings are supported / Oregon has no cap | No capacity check exists by design | Done |
