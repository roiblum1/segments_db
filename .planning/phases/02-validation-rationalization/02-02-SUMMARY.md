---
phase: 02-validation-rationalization
plan: 02
subsystem: api
tags: [validation, fastapi, pydantic, ipaddress, rfc3021]

# Dependency graph
requires:
  - phase: 02-validation-rationalization
    provides: dead validator removal and security_validators.py deletion (02-01)
provides:
  - EPG name regex ^[a-zA-Z0-9_\-\./]+$ accepting CIDR-format names (e.g. 192.168.1.0/24)
  - validate_subnet_mask supports /16 to /31 (up from /29)
  - validate_network_broadcast_gateway threshold num_addresses < 2 (down from 4)
  - Removed redundant usable_hosts check from validate_network_broadcast_gateway
affects: [segment-creation, operator-workflows, vlan-allocation]

# Tech tracking
tech-stack:
  added: []
  patterns: [RFC 3021 /31 point-to-point link support, CIDR-format EPG names]

key-files:
  created: []
  modified:
    - src/utils/validators/input_validators.py
    - src/utils/validators/network_validators.py

key-decisions:
  - "[02-02] EPG name allows dots and forward slashes -- operators routinely name segments after the prefix they represent (e.g. 192.168.1.0/24); NetBox has no VLAN name character restrictions"
  - "[02-02] /31 subnets allowed per RFC 3021 -- valid for point-to-point links; both addresses are usable"
  - "[02-02] Removed usable_hosts < 1 guard -- usable_hosts = num_addresses - 2 gives 0 for /31 (2 addresses), falsely triggering the guard; num_addresses < 2 is sufficient"

patterns-established:
  - "RFC 3021: /31 is valid for point-to-point links; treat 2-address networks as valid"
  - "Validator upper bounds should reflect real operator needs, not theoretical concerns"

requirements-completed: [VAL-05, VAL-06]

# Metrics
duration: 1min
completed: 2026-03-28
---

# Phase 2 Plan 02: Validation Rationalization (Input + Subnet) Summary

**EPG name regex relaxed to accept CIDR-format names (dots and slashes); subnet mask range expanded from /29 to /31 per RFC 3021, with redundant usable_hosts guard removed**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-28T10:07:54Z
- **Completed:** 2026-03-28T10:08:54Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- EPG name regex updated to `^[a-zA-Z0-9_\-\./]+$` — operators can now name segments after CIDR prefixes like `192.168.1.0/24`
- `validate_subnet_mask` upper bound raised from `/29` to `/31` with RFC 3021 reference in error message
- `validate_network_broadcast_gateway` threshold changed from `num_addresses < 4` to `< 2`, and the redundant `usable_hosts` guard fully removed
- `/30` and `/31` now pass both subnet validators; `/32` and `/15` remain correctly rejected

## Task Commits

Each task was committed atomically:

1. **Task 1: Update EPG name regex to accept dots and forward slashes** - `78aed92` (feat)
2. **Task 2: Expand subnet mask range to /31 in two network validators** - `3856d73` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `src/utils/validators/input_validators.py` - EPG name regex and error message updated
- `src/utils/validators/network_validators.py` - validate_subnet_mask upper bound /29 -> /31; validate_network_broadcast_gateway threshold 4 -> 2; usable_hosts check removed

## Decisions Made
- EPG names with dots and forward slashes allowed — operators routinely name segments after the prefix they represent; NetBox imposes no VLAN name character restrictions
- /31 subnets allowed per RFC 3021 — valid for point-to-point links where both addresses are usable
- `usable_hosts < 1` guard removed — it computed `num_addresses - 2` which equals 0 for /31 (2 addresses), falsely blocking valid point-to-point subnets; the `num_addresses < 2` check is sufficient

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 (Validation Rationalization) is fully complete — all 2 plans done
- All VAL requirements satisfied (VAL-05, VAL-06 this plan; VAL-01 through VAL-04 covered by 02-01)
- No blockers for subsequent phases

---
*Phase: 02-validation-rationalization*
*Completed: 2026-03-28*
