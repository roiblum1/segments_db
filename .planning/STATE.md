# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** Operators can create, allocate, and search VLANs and prefixes across any VRF+Site combination without polluting each other's data in NetBox.
**Current focus:** Phase 3: Database Layer Refactor

## Current Position

Phase: 3 of 3 (Database Layer Refactor)
Plan: 1 of 2 in current phase
Status: In progress
Last activity: 2026-03-28 -- 03-01 complete: database layer collapsed (netbox_segments.py + netbox_objects.py)

Progress: [█████░░░░░] 50%

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

| Phase                                | Total | Tasks | Files |
|--------------------------------------|-------|-------|-------|
| Phase 03-database-layer-refactor P01 | 5 min | 3     | 8     |

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
- [Phase 03]: [03-01] MongoDB query interpreter deleted — Python-native typed parameter filtering replaces _matches_query/_matches_condition (65 lines removed)
- [Phase 03]: [03-01] NetBoxHelpers renamed to NetBoxObjects; get_site renamed to get_site_group; get_redbull_tenant_id collapsed
- [Phase 03]: [03-01] 5 cache-key helpers moved from netbox_constants.py to netbox_utils.py; nb_client param removed from prefix_to_segment

### Roadmap Evolution

- Phase 3 added: Database Layer Refactor — collapse 8-file over-engineered database module into a clean, domain-named structure; remove MongoDB abstraction layer, dead code, and misleading names

### Pending Todos

None yet.

### Blockers/Concerns

- Production data migration: existing unscoped VLANs must be detected and migrated, not duplicated. Run audit query before deployment.
- Frontend XSS audit required before removing server-side XSS validators in Phase 2 (innerHTML usage in app.js must be verified).

## Session Continuity

Last session: 2026-03-28
Stopped at: Completed 03-01-PLAN.md (database layer collapse: netbox_segments.py + netbox_objects.py)
Resume file: None
