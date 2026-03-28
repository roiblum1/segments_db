---
phase: 02-validation-rationalization
plan: 01
subsystem: validation
tags: [cleanup, dead-code, security, validators]
dependency_graph:
  requires: []
  provides: [lean-validator-facade]
  affects: [src/utils/validators, src/services/segment_service]
tech_stack:
  added: []
  patterns: [dead-code-removal, facade-cleanup]
key_files:
  created: []
  modified:
    - src/utils/validators/__init__.py
    - src/utils/validators/organization_validators.py
    - src/utils/validators/data_validators.py
    - src/services/segment_service.py
  deleted:
    - src/utils/validators/security_validators.py
decisions:
  - "Removed wrong-threat-model security validators (XSS, path traversal, rate limiting) — internal REST API tool with trusted operators does not need them"
  - "Removed NoSQL injection checks ($ and __proto__ patterns) from validate_update_data — they are MongoDB-specific patterns meaningless against pynetbox/NetBox"
  - "Removed all dead methods with zero call sites: validate_concurrent_modification, validate_timezone_aware_datetime, validate_json_serializable, validate_update_data"
metrics:
  duration: 3 min
  completed: 2026-03-28
  tasks_completed: 2
  files_modified: 4
  files_deleted: 1
  lines_removed: 271
---

# Phase 2 Plan 1: Dead Validator Removal Summary

**One-liner:** Deleted security_validators.py and 4 dead validator methods, removing ~271 lines of wrong-threat-model and zero-call-site code from the validation layer.

## What Was Done

Removed two categories of validator code that provided no value to this internal REST API tool:

1. **Wrong-threat-model security validators** (`security_validators.py`, ~121 lines): XSS prevention, script injection detection, path traversal checks, and rate limit validation. These patterns assume an untrusted public internet user submitting HTML — operators using this internal tool are trusted, and NetBox stores data as plain text anyway.

2. **Dead validator methods** (zero call sites anywhere in the codebase):
   - `validate_concurrent_modification` — optimistic locking helper that was never invoked
   - `validate_timezone_aware_datetime` — datetime timezone check never invoked
   - `validate_json_serializable` — JSON serialization check never invoked
   - `validate_update_data` — bulk update validator exposed in facade but never called from any route or service

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Remove dead methods from organization_validators.py, data_validators.py, __init__.py | 0d9040a |
| 2 | Delete security_validators.py and clean all references from __init__.py and segment_service.py | a0d1f9a |

## Verification Results

- `security_validators.py` does not exist
- `grep` finds zero references to all removed symbols across all `.py` files under `src/`
- `from src.utils.validators import Validators` — imports cleanly
- `from src.services.segment_service import SegmentService` — imports cleanly
- `import src.app` — imports cleanly

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- Files deleted: `src/utils/validators/security_validators.py` — confirmed absent
- Commits: `0d9040a` and `a0d1f9a` — confirmed present in git log
- Zero grep matches for all removed symbols — confirmed
- All three import checks pass — confirmed
