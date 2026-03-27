# Domain Pitfalls

**Domain:** NetBox VLAN scoping bug fix + validation relaxation
**Researched:** 2026-03-27
**Confidence:** HIGH (based on direct code analysis of the production codebase)

## Critical Pitfalls

### Pitfall 1: Global VLAN Lookup Returns Wrong VLAN When Scoping to Groups

**What goes wrong:** The current `get_or_create_vlan()` in `netbox_helpers.py` (line 155-158) searches VLANs globally by VID only: `vlan_filter = {"vid": vlan_id}`. When fixing VLAN scoping, if you change the lookup to filter by VLAN Group but existing VLANs in NetBox were created WITHOUT a group assignment, the lookup will miss them. The code will then create a duplicate VLAN with the same VID (now scoped to a group), leaving the old unscoped VLAN orphaned and still attached to existing prefixes.

**Why it happens:** Existing production data has VLANs created without VLAN Group assignments. The fix introduces group-scoped lookups, but the old data doesn't match.

**Consequences:**
- Duplicate VLAN objects in NetBox (one unscoped, one scoped) for the same VID
- Existing prefixes still reference the old unscoped VLAN
- EPG name searches return stale data from the wrong VLAN object
- NetBox uniqueness constraints may be violated if two VLANs have the same name in the same group

**Prevention:**
1. The fix MUST include a migration path: when an existing unscoped VLAN is found, move it into the correct VLAN Group rather than creating a new one
2. The lookup should try group-scoped first, then fall back to global lookup with group reassignment
3. Add a one-time migration script or on-demand migration in `get_or_create_vlan()` that assigns groups to existing unscoped VLANs

**Detection:** After deploying, query `nb.ipam.vlans.filter(group__isnull=True, tenant="RedBull")` -- any results are orphaned VLANs that need migration.

**Phase:** Must be addressed in the VLAN scoping fix phase. This IS the core fix.

---

### Pitfall 2: Cache Serves Stale VLAN Data After Scoping Change

**What goes wrong:** The prefix cache (`CACHE_KEY_PREFIXES`, 10-minute TTL) and VLAN cache (`CACHE_KEY_VLANS`, 10-minute TTL) contain pre-fix data. After updating VLAN group assignments, the cache still holds old VLAN objects without group info. The `cleanup_unused_vlan()` method (line 97-134 in `netbox_helpers.py`) checks cached prefixes to decide if a VLAN is safe to delete -- stale cache could cause it to incorrectly delete a VLAN that IS still in use by a prefix not yet in cache.

**Why it happens:** `cleanup_unused_vlan()` explicitly relies on cached prefix data (line 112: `cached_prefixes = get_cached(CACHE_KEY_PREFIXES)`). If a prefix was just created or reassigned but the cache hasn't been refreshed, the check is wrong.

**Consequences:**
- A VLAN gets deleted while a prefix still references it
- NetBox may allow this (soft reference) but the prefix loses its VLAN association
- EPG name disappears from the prefix, breaking the UI display

**Prevention:**
1. After ANY VLAN group reassignment, invalidate BOTH `CACHE_KEY_PREFIXES` and `CACHE_KEY_VLANS`
2. In `cleanup_unused_vlan()`, if cache is stale (None), do a real API call rather than silently skipping cleanup -- the current "skip cleanup" behavior (line 114) is safer but means orphaned VLANs accumulate
3. Consider invalidating cache at the START of the VLAN scoping fix operation, not just at the end

**Detection:** Monitor for prefixes with `vlan: null` in NetBox that previously had VLAN assignments.

**Phase:** Must be addressed alongside the VLAN scoping fix.

---

### Pitfall 3: Race Condition in get_or_create_vlan() With Group Scoping

**What goes wrong:** Two concurrent requests for the same VLAN ID + different sites hit `get_or_create_vlan()` simultaneously. With the current global lookup (`vid=vlan_id`), request A finds no VLAN and creates one scoped to Site1's group. Request B, running concurrently, also finds no VLAN (the first hasn't been committed yet) and tries to create another scoped to Site2's group. If both succeed, you may end up with two VLANs with the same VID but different groups -- which is actually correct. But if both target the SAME site, you get a NetBox uniqueness violation (`group` + `vid` must be unique).

**Why it happens:** No locking or request coalescing exists for VLAN creation. The cache coalescing in `netbox_cache.py` only protects prefix reads, not VLAN writes.

**Consequences:**
- `pynetbox` raises an exception on the duplicate create attempt
- The retry decorator (`@retry_on_network_error`) retries the same conflicting operation 3 times
- User sees a 500 error for a legitimate operation

**Prevention:**
1. Wrap `get_or_create_vlan()` in a try/except that catches the uniqueness violation and retries with a GET (the other request's VLAN now exists)
2. The pattern should be: GET by (group_id, vid) -> if not found, CREATE -> if CREATE fails with uniqueness error, GET again
3. This is the standard "get or create with race condition handling" pattern

**Detection:** Look for `pynetbox.RequestError` with "duplicate" or "unique" in the error message in logs.

**Phase:** Must be addressed in the VLAN scoping fix phase.

---

### Pitfall 4: Relaxing EPG Name Validation Breaks NetBox VLAN Name Constraints

**What goes wrong:** The EPG name is used as the VLAN `name` field in NetBox (see `netbox_helpers.py` line 165: `"name": name`). NetBox VLAN names have their own constraints (max 64 chars, certain character restrictions depending on NetBox version). If you relax validation to allow CIDR-format names like `192.168.1.0/24`, the forward slash `/` may or may not be accepted by NetBox depending on the version. If NetBox rejects it, the user gets an opaque pynetbox error instead of a clear validation message.

**Why it happens:** The current regex `^[a-zA-Z0-9_\-]+$` in `input_validators.py` line 63 blocks dots and slashes. Removing this regex entirely means trusting NetBox's validation. But NetBox's error messages via pynetbox are not user-friendly -- they come as raw API error responses.

**Consequences:**
- User tries to create EPG with CIDR name, NetBox rejects it silently
- Error message is something like `{"name": ["Enter a valid value"]}` rather than a clear instruction
- The `_sanitize_slug()` function in `netbox_helpers.py` strips non-alphanumeric chars from VLAN Group slugs, but VLAN names go through differently

**Prevention:**
1. Before removing the regex entirely, verify what characters NetBox actually accepts for VLAN names by testing against the target NetBox instance
2. Replace the strict regex with a permissive one that allows dots and slashes: `^[a-zA-Z0-9_\-\./]+$`
3. Keep the 64-char max length check (NetBox enforces this too, but with a worse error message)
4. Add error translation in `error_handlers.py` to convert pynetbox validation errors into user-friendly messages

**Detection:** Test creating a VLAN with name `192.168.1.0/24` directly via pynetbox or the NetBox API before deploying.

**Phase:** Must be addressed in the validation relaxation phase. Test BEFORE removing validators.

## Moderate Pitfalls

### Pitfall 5: Removing XSS Validation Without Escaping in the Frontend

**What goes wrong:** The web UI in `static/js/app.js` may be inserting EPG names and descriptions directly into the DOM using `innerHTML` or similar. If XSS validation is removed server-side without ensuring the frontend escapes output, you trade one problem (can't enter valid data) for another (stored XSS via EPG name or description).

**Prevention:**
1. Audit `static/js/app.js` for uses of `innerHTML`, `document.write()`, `jQuery.html()` -- replace with `textContent` or proper escaping
2. Even for an internal tool, stored XSS is a risk if the NetBox token has write permissions -- an XSS payload could automate destructive actions via the API
3. Remove server-side XSS checks AFTER confirming frontend output escaping is in place

**Detection:** Search `app.js` for `innerHTML` usage and test with `<script>alert(1)</script>` as an EPG name after the fix.

**Phase:** Address in validation relaxation phase, but audit frontend first.

---

### Pitfall 6: delete_one() Unconditionally Deletes VLANs Without Group Awareness

**What goes wrong:** The current `delete_one()` in `netbox_crud_ops.py` (line 258-313) deletes the associated VLAN whenever a prefix is deleted. After the scoping fix, a VLAN in a VLAN Group might be shared by multiple prefixes (if the business logic allows this in the future). Deleting the VLAN when the first prefix is removed would break the other prefixes.

**Why it happens:** The current code assumes 1:1 prefix-to-VLAN mapping. The `cleanup_unused_vlan()` method checks for this, but `delete_one()` bypasses it entirely (line 295-302) and calls `vlan_obj.delete()` directly without checking if other prefixes use it.

**Prevention:**
1. Change `delete_one()` to use `cleanup_unused_vlan()` instead of direct deletion
2. Or add a prefix count check before VLAN deletion: query NetBox for prefixes with this VLAN ID, only delete if count == 0 (the prefix being deleted is already gone at this point)

**Detection:** After deleting a prefix, check if other prefixes in the same VLAN Group lost their VLAN association.

**Phase:** Should be addressed in the VLAN scoping fix phase since group scoping changes the VLAN lifecycle.

---

### Pitfall 7: VLAN Group Name Format Assumes Capitalized Site Names

**What goes wrong:** `format_vlan_group_name()` in `netbox_constants.py` creates names like `Network1-ClickCluster-Site1`. The `get_or_create_vlan()` method capitalizes the site slug (line 183: `site_group = site_slug.capitalize()`). If site slugs in NetBox are lowercase (e.g., `site1` not `Site1`), the VLAN Group name won't match existing groups, causing duplicate groups with different capitalizations.

**Prevention:**
1. Standardize site slug normalization in ONE place -- either always capitalize or always lowercase
2. The `get_site()` method already handles both cases (lines 56-95), so use whatever slug NetBox returns as the canonical form
3. When looking up VLAN Groups, do a case-insensitive search or normalize consistently

**Detection:** Query `nb.ipam.vlan_groups.all()` and look for near-duplicate names differing only in capitalization.

**Phase:** Address during VLAN scoping fix.

---

### Pitfall 8: IP Overlap Validation Fetches ALL Segments on Every Create

**What goes wrong:** Not directly related to the scoping fix, but `_validate_segment_data()` (segment_service.py line 40) calls `DatabaseUtils.get_segments_with_filters()` to get ALL segments for overlap checking. This is fine with cache hits, but after cache invalidation from the VLAN scoping changes, every create triggers a full NetBox fetch. In bulk operations, this means N full fetches if the cache is invalidated between creates.

**Prevention:**
1. The bulk create path (line 283) already fetches once -- ensure single creates don't invalidate cache mid-validation
2. Consider scoping the overlap check to the same VRF+Site instead of all segments

**Detection:** Watch for slow create operations (>2s) after deploying the fix. Check logs for cache MISS patterns.

**Phase:** Minor optimization, can be deferred. Not blocking.

## Minor Pitfalls

### Pitfall 9: Removing validate_no_reserved_ips() May Allow Loopback/Link-Local Segments

**What goes wrong:** If `validate_no_reserved_ips()` is removed as part of "trust NetBox" approach, users could create prefixes like `127.0.0.1/8` or `169.254.0.0/16`. NetBox does accept these as valid prefixes -- they ARE valid CIDR. But they are nonsensical for VLAN allocation.

**Prevention:** Keep `validate_no_reserved_ips()` -- this is business logic, not format validation. NetBox does not enforce "this prefix makes sense for your use case."

**Detection:** Review which validators are actually redundant with NetBox vs which encode business rules.

**Phase:** Validation relaxation phase. Categorize each validator before removing.

---

### Pitfall 10: Test Suite Uses Hardcoded Site/VRF Names That May Not Match After Fix

**What goes wrong:** The test suite (`test_api.py`) uses hardcoded values like `"Site1"`, `"Network1"`, `192.1.80.0/24`. After the scoping fix, if VLAN Group naming or site slug handling changes, tests may pass locally but fail in CI where the NetBox instance has different data.

**Prevention:**
1. Add tests specifically for the VLAN scoping behavior: create same VLAN ID in two different sites, verify they get separate VLAN objects in separate VLAN Groups
2. Add tests for CIDR-format EPG names
3. Add tests that verify relaxed validation still rejects truly invalid input

**Detection:** Run full test suite against a NetBox instance with production-like data after the fix.

**Phase:** Both phases need new tests.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| VLAN scoping fix | Orphaned unscoped VLANs in production data (Pitfall 1) | Migration-aware lookup: find unscoped, assign to group |
| VLAN scoping fix | Cache inconsistency during migration (Pitfall 2) | Invalidate ALL caches before and after migration ops |
| VLAN scoping fix | Race condition on concurrent VLAN creation (Pitfall 3) | Get-or-create with retry on uniqueness violation |
| VLAN scoping fix | delete_one() kills shared VLANs (Pitfall 6) | Use cleanup_unused_vlan() pattern instead of direct delete |
| VLAN scoping fix | Site slug capitalization inconsistency (Pitfall 7) | Normalize site slugs consistently |
| Validation relaxation | CIDR EPG names rejected by NetBox (Pitfall 4) | Test against actual NetBox before removing validators |
| Validation relaxation | XSS vectors opened in frontend (Pitfall 5) | Audit frontend for innerHTML before removing server checks |
| Validation relaxation | Reserved IP check removed incorrectly (Pitfall 9) | Keep business-logic validators, only remove format-check duplicates |
| Both phases | Test coverage gaps (Pitfall 10) | Write scoping and relaxed-validation tests before changing code |

## Sources

- Direct code analysis of the production codebase at `/Users/roiblum/Downloads/scripts/segments_2/`
- NetBox VLAN uniqueness constraints: NetBox enforces unique (group, vid) and unique (group, name) for VLANs -- HIGH confidence from pynetbox behavior and NetBox data model
- pynetbox error handling: pynetbox raises `RequestError` on API validation failures -- HIGH confidence from library behavior
