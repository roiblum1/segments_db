# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** Operators can create, allocate, and search VLANs and prefixes across any VRF+Site combination without polluting each other's data in NetBox.
**Current focus:** Phase 2: Validation Rationalization

## Current Position

Phase: 2 of 2 (Validation Rationalization)
Plan: 2 of 2 in current phase
Status: Complete
Last activity: 2026-03-28 -- Completed 02-02-PLAN.md (EPG regex + subnet mask range relaxation)

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 1
- Average duration: 2 min
- Total execution time: 0.03 hours

**By Phase:**

| Phase                           | Plans | Total | Avg/Plan |
|---------------------------------|-------|-------|----------|
| 01-vlan-site-isolation          | 1     | 2 min | 2 min    |
| 02-validation-rationalization   | 2     | 4 min | 2 min    |

**Recent Trend:**
- Last 5 plans: 1 min
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- VLAN must be scoped to VLAN Group (site-specific) -- root cause of collision bug
- Remove XSS validation -- internal tool, operators are trusted
- Trust NetBox for non-critical field validation -- reduces maintenance burden
- [01-01] Group resolution is step one, not a fallback -- eliminates cross-site VLAN sharing
- [01-01] No silent unscoped VLAN creation -- missing site_slug/vrf_name raises HTTP 400
- [01-01] Audit script is read-only -- operators remediate existing unscoped VLANs manually via UI/API
- [02-01] Deleted security_validators.py -- XSS/path-traversal/rate-limit checks are wrong threat model for an internal REST API tool with trusted operators
- [02-01] Removed NoSQL injection checks ($ and __proto__ patterns) from validate_update_data -- MongoDB-specific patterns meaningless against pynetbox/NetBox
- [02-01] Removed 4 dead validator methods with zero call sites -- `validate_concurrent_modification`, `validate_timezone_aware_datetime`, `validate_json_serializable`, `validate_update_data`
- [Phase 02-02]: [02-02] EPG name allows dots and forward slashes -- operators routinely name segments after the prefix they represent; NetBox has no VLAN name character restrictions
- [Phase 02-02]: [02-02] /31 subnets allowed per RFC 3021 -- valid for point-to-point links; num_addresses < 2 threshold is sufficient, usable_hosts guard removed

### Pending Todos

None yet.

### Blockers/Concerns

- Production data migration: existing unscoped VLANs must be detected and migrated, not duplicated. Run audit query before deployment.
- Frontend XSS audit required before removing server-side XSS validators in Phase 2 (innerHTML usage in app.js must be verified).

## Session Continuity

Last session: 2026-03-28
Stopped at: Completed 02-02-PLAN.md (EPG regex + subnet mask range relaxation)
Resume file: None
