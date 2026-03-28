---
phase: 03-database-layer-refactor
plan: "01"
subsystem: database
tags: [netbox, pynetbox, refactor, database, segments, prefixes, vlan]

# Dependency graph
requires:
  - phase: 02-validation-rationalization
    provides: cleaned-up validators and relaxed rules that callers depend on
provides:
  - netbox_segments.py — 7 domain async functions for segment CRUD + allocation
  - netbox_objects.py — NetBoxObjects class with get_site_group (renamed from netbox_helpers)
  - netbox_storage.py — lifecycle-only (init_storage, close_storage, prefetch_reference_data)
  - __init__.py — clean domain function exports (no MongoDB-shim class)
affects:
  - 03-02-callers — src/utils/database_utils.py and services that import get_storage/NetBoxStorage must be updated

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level singleton pattern: _nb and _objects initialized by init_segments_module()"
    - "Typed-parameter filtering: Python-native conditionals replace MongoDB query interpreter"
    - "Functions-first database module: no class wrappers around domain operations"

key-files:
  created:
    - src/database/netbox_segments.py
    - src/database/netbox_objects.py
  modified:
    - src/database/netbox_storage.py
    - src/database/__init__.py
    - src/database/netbox_client.py
    - src/database/netbox_cache.py
    - src/database/netbox_utils.py
    - src/database/netbox_constants.py
  deleted:
    - src/database/netbox_crud_ops.py
    - src/database/netbox_query_ops.py
    - src/database/netbox_helpers.py

key-decisions:
  - "MongoDB query interpreter deleted — 65 lines of _matches_query/_matches_condition replaced with _segment_matches() using typed Python parameters"
  - "NetBoxHelpers renamed to NetBoxObjects; get_site renamed to get_site_group to match what the method actually does"
  - "get_redbull_tenant_id() collapsed — callers call get_tenant(TENANT_REDBULL).id directly"
  - "5 cache-key helpers moved from netbox_constants.py (wrong home) to netbox_utils.py (right home)"
  - "Plan's file count assertion (7) was incorrect — the refactor produces 8 files (includes netbox_storage.py); verified all expected files present"

patterns-established:
  - "Module-level init pattern: init_segments_module(nb_client) wires the module at startup via init_storage()"
  - "1-arg prefix_to_segment: nb_client parameter removed since it was never used in the function body"

requirements-completed: [DB-01, DB-02, DB-03, DB-04, DB-05]

# Metrics
duration: 5min
completed: 2026-03-28
---

# Phase 3 Plan 01: Database Layer Collapse Summary

**4-file MongoDB-shim layer (crud_ops, query_ops, helpers, storage class) collapsed into 2 clean domain files (netbox_segments.py, netbox_objects.py) plus lifecycle-only netbox_storage.py; 65-line MongoDB query interpreter deleted; dead code and misplaced utility functions cleaned up**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-28T19:37:15Z
- **Completed:** 2026-03-28T19:42:30Z
- **Tasks:** 3
- **Files modified:** 8 (6 modified, 2 created, 3 deleted)

## Accomplishments
- Created `netbox_segments.py` merging crud_ops + query_ops: 7 domain async functions + init_segments_module, zero MongoDB operators
- Created `netbox_objects.py` as renamed/cleaned netbox_helpers.py: class rename NetBoxHelpers→NetBoxObjects, get_site→get_site_group, get_redbull_tenant_id removed
- Deleted netbox_crud_ops.py, netbox_query_ops.py, netbox_helpers.py (~950 lines of replaced code)
- Removed `log_netbox_timing` decorator (33 lines) and `get_netbox_executor` (4 lines) from netbox_client.py
- Removed 3 unused cache pre-declarations from netbox_cache.py
- Moved 5 cache-key functions from netbox_constants.py to netbox_utils.py; removed nb_client param from prefix_to_segment

## Task Commits

Each task was committed atomically:

1. **Task 1: Create netbox_segments.py and netbox_objects.py** - `e3f3983` (feat)
2. **Task 2: Trim netbox_client.py, netbox_cache.py, netbox_utils.py, netbox_constants.py** - `e947550` (refactor)
3. **Task 3: Rewrite netbox_storage.py, update __init__.py, delete 3 old files** - `aacbdbb` (refactor)

## Files Created/Modified
- `src/database/netbox_segments.py` (NEW) — Domain segment CRUD/query: get_segments, get_segment_by_id, create_segment, update_segment, delete_segment, allocate_segment, get_vrfs
- `src/database/netbox_objects.py` (NEW) — Renamed from netbox_helpers.py; NetBoxObjects with get_site_group
- `src/database/netbox_storage.py` — Lifecycle only: init_storage calls init_segments_module(); NetBoxStorage class deleted
- `src/database/__init__.py` — Exports domain functions; NetBoxStorage and get_storage removed
- `src/database/netbox_client.py` — Removed log_netbox_timing and get_netbox_executor; removed wraps import
- `src/database/netbox_cache.py` — Removed 3 unused pre-declared cache entries
- `src/database/netbox_utils.py` — prefix_to_segment is now 1-arg; absorbed 5 cache-key helpers from constants
- `src/database/netbox_constants.py` — Pure constants only; 5 functions moved out

## Decisions Made
- Collapsed `get_redbull_tenant_id()` as noted in RESEARCH Pitfall 3 — callers use `get_tenant(TENANT_REDBULL).id` directly
- Non-atomicity documented in allocate_segment docstring per plan requirement — fix is explicitly out of scope

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan assertion `len(db_files) == 7` was incorrect**
- **Found during:** Task 3 verification
- **Issue:** Plan's must_haves.truths and verification script state "exactly 7 files" but the plan itself lists 8 files in the verification file tree (the 7 listed + netbox_storage.py which is kept). The number 7 omitted netbox_storage.py from the count.
- **Fix:** Verified actual file set matches the plan's file tree exactly; noted the count assertion was off-by-one. All 8 expected files present, no extra files.
- **Files modified:** None — this was a plan wording discrepancy, not a code issue.

---

**Total deviations:** 1 (plan wording discrepancy in file count assertion)
**Impact on plan:** Zero impact. All 8 correct files are present and the structure matches the plan's file tree exactly.

## Issues Encountered
- grep dead-code check against `src/database/` matched `.pyc` binary files in `__pycache__` (old compiled bytecache). Re-ran with `--include="*.py"` which confirmed no dead code in source files.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `src/database/` module is fully refactored with clean domain interface
- **BLOCKER:** `src/utils/database_utils.py` and all services still call `get_storage()` / `NetBoxStorage` methods — these must be updated in plan 03-02 before the application can start
- Do not attempt to run the server after 03-01 alone; 03-02 is required

---
*Phase: 03-database-layer-refactor*
*Completed: 2026-03-28*

## Self-Check: PASSED

All created/modified files verified present. All deleted files confirmed absent. All task commits verified in git log.
