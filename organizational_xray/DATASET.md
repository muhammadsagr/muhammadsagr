# Dataset report (generated)

> مولَّد تلقائيًا بالأمر `python -m data.dummy_generator` — كل الأرقام محسوبة من البيانات نفسها. أعد تشغيل الأمر بعد تغيير الـseed أو الحجم.

## Dataset facts (computed)
- Records: 1,543
- Active employees (headcount): 1,474
- Vacant positions: 66
- Terminated records still referenced: 2
- Business units / divisions / departments: 4 / 7 / 24
- Managers (>= 1 active direct report): 222
- Structural layers: 9 (depth 1–8, mean 5.68, median 6)
- Span of control: min 1, P25 3, median 6, mean 6.51, P75 10, max 32
- Findings (default settings): 199

| Finding type | Count |
|---|---|
| CIRCULAR_REPORTING | 2 |
| DEEP_HIERARCHY | 1 |
| DUPLICATE_POSITION | 11 |
| HIGH_MANAGEMENT_RATIO | 4 |
| HIGH_SPAN_OF_CONTROL | 13 |
| INVALID_MANAGER | 3 |
| LOW_SPAN_OF_CONTROL | 87 |
| ORPHAN_EMPLOYEE | 3 |
| SMALL_DEPARTMENT | 6 |
| TERMINATED_MANAGER | 2 |
| VACANT_POSITION | 67 |

| Severity | Count |
|---|---|
| Informational | 156 |
| Attention | 24 |
| Significant | 16 |
| Critical | 3 |

## Injected issues (generator manifest)

| Issue | Expected finding | Department | IDs |
|---|---|---|---|
| Missing Manager ID | ORPHAN_EMPLOYEE | Sales | E10472 |
| Missing Manager ID | ORPHAN_EMPLOYEE | Infrastructure | E13751 |
| Missing Manager ID | ORPHAN_EMPLOYEE | Supply Chain | E13695 |
| Manager ID not found | INVALID_MANAGER | Talent Acquisition | E13885 |
| Manager ID not found | INVALID_MANAGER | Applications | E11903 |
| Manager ID not found | INVALID_MANAGER | Customer Operations | E12308 |
| Reports point to a terminated manager | TERMINATED_MANAGER | Customer Operations | E10060, E13517, E11581, E13378 … |
| Reports point to a terminated manager | TERMINATED_MANAGER | Marketing | E13177, E11501, E10932, E10137 … |
| Circular reporting (3-cycle) | CIRCULAR_REPORTING | Marketing | E12153, E10591, E11958 |
| Self-reporting (1-cycle) | CIRCULAR_REPORTING | Data & Analytics | E10195 |
| Duplicate Position ID | DUPLICATE_POSITION | Accounting | E11241, E13285 |
| Duplicate Position ID | DUPLICATE_POSITION | Sales | E12592, E11582 |
| Manager-level position with no active reports (team vacant) | VACANT_POSITION | Applications | E14585 |
| Job title case variant ('hr analyst') | DUPLICATE_POSITION | HR Operations | E11816 |
| Missing job title | DATA_QUALITY | Procurement | E14452 |
| Missing job title | DATA_QUALITY | Quality | E11829 |
| Missing salary | DATA_QUALITY | Supply Chain | E11236 |
| Missing salary | DATA_QUALITY | Customer Operations | E10574 |
| Missing salary | DATA_QUALITY | Sales | E14129 |
| Salary = 0 | DATA_QUALITY | Operations | E11312 |
| Missing department | DATA_QUALITY | Applications | E14234 |
| Duplicate Employee ID | DATA_QUALITY | Accounting | E13478 |
