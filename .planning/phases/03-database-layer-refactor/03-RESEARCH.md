# Phase 3: Database Layer Refactor - Research

**Researched:** 2026-03-28
**Domain:** Python internal refactoring — no new libraries; code structure, naming, dead code elimination
**Confidence:** HIGH (all findings are based on direct source code inspection of the actual files)

## Summary

The `src/database/` module grew from a MongoDB-backed design that was later ported to NetBox. The port preserved the MongoDB method names (`find`, `insert_one`, `update_one`, `find_one_and_update`, `count_documents`) and query language (`$or`, `$regex`, `$ne`, `$set`) as a compatibility shim. That shim now costs 65 lines of query-interpreter code (in `netbox_query_ops.py`) and requires every caller to speak MongoDB syntax to a backend that is actually pynetbox REST calls. The shim adds no value and makes the code harder to read.

The module is split across 9 files. The split was introduced as a refactoring but the boundaries were chosen by operation type (CRUD vs query vs helpers) rather than by domain. The result is that related operations are scattered: VLAN/VLAN Group writes are in `netbox_helpers.py`, prefix writes are in `netbox_crud_ops.py`, prefix reads are in `netbox_query_ops.py`, and the `NetBoxStorage` class in `netbox_storage.py` is a pure pass-through with no logic. Meanwhile `netbox_constants.py` contains 5 utility functions that don't belong there.

The goal of this phase is to collapse 9 files to 6 by deleting dead code, merging the pass-through facade into a thin module-level API, grouping by domain (segments vs NetBox objects), and moving helpers to their rightful home. No behaviour changes. The entire change is visible to callers only through the intermediate `src/utils/database/` layer, which will need its MongoDB query calls replaced with direct domain method calls.

**Primary recommendation:** Merge crud+query+storage into `netbox_segments.py`, rename helpers to `netbox_objects.py` for honest naming, move cache-key functions from constants to utils, delete all dead code. Update `src/utils/database/*.py` callers to use domain methods directly.

## Current File Inventory (Verified by Direct Inspection)

### `src/database/` — 9 files

| File | Lines | What it actually does |
|------|-------|-----------------------|
| `__init__.py` | 16 | Exports `NetBoxStorage`, `get_storage`, `init_storage`, `close_storage` |
| `netbox_storage.py` | 137 | `prefetch_reference_data()`, `init_storage()`, `close_storage()` (real work); `NetBoxStorage` class (pure delegation to crud/query/helpers); `get_storage()` creates new instance every call |
| `netbox_crud_ops.py` | 346 | Prefix writes: `insert_one`, `update_one`, `delete_one`, `find_one_and_update` (all prefix-only) |
| `netbox_query_ops.py` | 194 | Prefix reads: `find`, `find_one`, `count_documents`; 65-line MongoDB query interpreter (`_matches_query`, `_matches_condition`) |
| `netbox_helpers.py` | 349 | NetBox object helpers: `get_site`, `get_vrf`, `get_tenant`, `get_role`, `get_vrfs`; VLAN/VLAN Group writes: `get_or_create_vlan`, `get_or_create_vlan_group`, `cleanup_unused_vlan`; `get_redbull_tenant_id` dedicated wrapper |
| `netbox_client.py` | 140 | Client init/singleton, `run_netbox_get`, `run_netbox_write`, thread pools; DEAD: `log_netbox_timing` decorator (33 lines, never applied), `get_netbox_executor` (3 lines, never called) |
| `netbox_cache.py` | 104 | TTL cache, inflight request tracking; 3 pre-declared entries (`"site_groups"`, `"roles"`, `"tenants"`) are never accessed anywhere |
| `netbox_utils.py` | 147 | `safe_get_attr`, `safe_get_id`, `ensure_custom_fields`, `get_custom_field`, `set_custom_field`, `get_site_slug_from_prefix`, `get_vlan_info`, `prefix_to_segment`; DEAD PARAM: `nb_client` in `prefix_to_segment` is passed but never used inside the function |
| `netbox_constants.py` | 62 | True constants (strings, integers); MISPLACED: 5 utility functions (`get_tenant_cache_key`, `get_role_cache_key`, `get_site_group_cache_key`, `get_vlan_group_cache_key`, `format_vlan_group_name`) that do not belong in a constants file |

**Total: ~1,500 lines across 9 files**

### `src/utils/database/` — 5 files (the caller layer)

| File | What it does | MongoDB syntax used |
|------|--------------|---------------------|
| `segment_crud.py` | `create_segment`, `get_segment_by_id`, `update_segment_by_id`, `delete_segment_by_id` | `insert_one`, `find_one`, `update_one` (with `$set`), `delete_one` |
| `allocation_utils.py` | Allocation, release, find_existing | `find_one`, `find_one_and_update` (with `$set`), `update_one` (with `$set`); query uses `$regex`, `$or`, `$ne` |
| `segment_queries.py` | Filters, search, VLAN existence checks | `find`, `find_one`; queries use `$ne`, `$regex`, `$or` |
| `statistics_utils.py` | Site stats | `find` only |
| `__init__.py` | `DatabaseUtils` aggregation class | Delegates to the above |

**Total: ~350 lines across 5 files**

### Other callers using `get_storage()` directly

- `src/utils/validators/organization_validators.py` — calls `storage.get_vrfs()` for VRF validation

## Dead Code Confirmed

| Item | Location | Evidence of Dead |
|------|----------|-----------------|
| `log_netbox_timing` decorator | `netbox_client.py:71` | Grep finds zero usages outside its own definition |
| `get_netbox_executor()` | `netbox_client.py:46` | Grep finds zero callers; docstring says "for backward compatibility" |
| `"site_groups"` cache pre-declaration | `netbox_cache.py:28` | Key never passed to `get_cached()` or `set_cache()` outside this file |
| `"roles"` cache pre-declaration | `netbox_cache.py:29` | Same — never accessed |
| `"tenants"` cache pre-declaration | `netbox_cache.py:30` | Same — never accessed |
| `nb_client` parameter in `prefix_to_segment` | `netbox_utils.py:87` | Parameter is accepted but body never references it |

## Misleading Names Confirmed

| Current Name | What it Actually Does | Better Name |
|---|---|---|
| `get_site()` in `NetBoxHelpers` | Fetches a `dcim.site_groups` object, not a `dcim.sites` object | `get_site_group()` |
| `NetBoxStorage` class | Pure delegation; no storage logic; it's a facade | Eliminate — expose module-level functions directly |
| `netbox_helpers.py` | Does writes (VLAN create/update/delete) as well as reads | `netbox_objects.py` — helpers for NetBox reference objects |
| `netbox_crud_ops.py` | Prefix operations only (not general CRUD) | Merge into `netbox_segments.py` |
| `netbox_query_ops.py` | Prefix queries only (not general queries) | Merge into `netbox_segments.py` |

## MongoDB Query Interpreter — Full Mapping

The `_matches_query` / `_matches_condition` methods in `netbox_query_ops.py` implement these operators:

| MongoDB operator | Used in callers | Replacement |
|-----------------|-----------------|-------------|
| `{"$ne": value}` | `segment_queries.py` (cluster_name != None), `allocation_utils.py` | Direct Python: `segment.get("cluster_name") is not None` |
| `{"$regex": pat, "$options": "i"}` | `allocation_utils.py` (shared cluster match), `segment_queries.py` (text search) | `re.search(pat, value, re.IGNORECASE)` inline |
| `{"$or": [...]}` | `segment_queries.py` (search across multiple fields) | Python `any()` over conditions |
| `{"$set": {...}}` | All write callers | Pass `updates` dict directly to domain method |

After replacing the MongoDB API with domain methods in `src/utils/database/`, the entire `_matches_query` / `_matches_condition` interpreter can be deleted. The filtering logic that remains in `netbox_segments.py` will only need to handle the actual field comparisons that `find()` already does correctly.

## Caller Impact Matrix

Every caller in `src/utils/database/` calls `get_storage()` and then uses MongoDB verbs. After refactoring, callers import domain functions directly.

| Current call | Replacement |
|---|---|
| `storage.insert_one(doc)` | `create_segment(doc)` |
| `storage.find_one({"_id": id})` | `get_segment_by_id(id)` |
| `storage.find(query)` | `get_segments(filters...)` with Python-typed parameters |
| `storage.update_one({"_id": id}, {"$set": data})` | `update_segment(id, data)` |
| `storage.delete_one({"_id": id})` | `delete_segment(id)` |
| `storage.find_one_and_update(q, {"$set": data}, sort=...)` | `allocate_segment(site, vrf, cluster_name, sort_by_vlan_id=True)` |
| `storage.count_documents(q)` | Replace with `len(get_segments(...))` — only called from count-based stat code |
| `storage.get_vrfs()` | `get_vrfs()` module-level function |
| `{"cluster_name": {"$ne": None}}` filter | `allocated=True` boolean parameter |
| `{"cluster_name": None}` filter | `allocated=False` boolean parameter |
| `{"$regex": ...}` in search_conditions | Inline `re.search()` in `search_segments()` |
| `{"$or": search_conditions}` | `any()` over Python condition list |

## Architecture Patterns

### Target File Structure

```
src/database/
├── __init__.py          # Exports: init_storage, close_storage, get_segment_by_id,
│                        #   get_segments, create_segment, update_segment, delete_segment,
│                        #   allocate_segment, get_vrfs
├── netbox_client.py     # Keep minus dead code: remove log_netbox_timing (33 lines),
│                        #   get_netbox_executor (3 lines)
├── netbox_cache.py      # Keep minus 3 unused pre-declared entries
├── netbox_segments.py   # NEW: merge of netbox_crud_ops + netbox_query_ops +
│                        #   delegation parts of netbox_storage
│                        #   Module-level functions, no class wrapper needed
├── netbox_objects.py    # RENAMED from netbox_helpers.py with get_site renamed
│                        #   to get_site_group
├── netbox_utils.py      # Keep: remove dead nb_client param; absorb 5 cache-key
│                        #   functions from netbox_constants.py
└── netbox_constants.py  # Keep: true constants only (remove 5 functions)
```

**From 9 files to 6 files** (including `__init__.py`). The `netbox_storage.py` file disappears entirely — its `prefetch_reference_data`/`init_storage`/`close_storage` functions move to `netbox_segments.py` or remain in a thin `netbox_storage.py` that only exports the 3 lifecycle functions (no class).

### Pattern: Module-Level Functions Instead of Class Facade

The `NetBoxStorage` class is a pass-through with no state of its own (it holds `self.nb`, `self.helpers`, `self.crud_ops`, `self.query_ops` but these are created fresh each call since `get_storage()` creates a new instance every time). Replace with module-level functions:

```python
# netbox_segments.py
async def get_segments(
    site: Optional[str] = None,
    vrf: Optional[str] = None,
    vlan_id: Optional[int] = None,
    allocated: Optional[bool] = None,
    cluster_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch all segments with optional filters. Handles caching and coalescing."""
    ...

async def get_segment_by_id(segment_id: str) -> Optional[Dict[str, Any]]:
    ...

async def create_segment(document: Dict[str, Any]) -> Dict[str, Any]:
    ...

async def update_segment(segment_id: str, updates: Dict[str, Any]) -> bool:
    ...

async def delete_segment(segment_id: str) -> bool:
    ...

async def allocate_segment(
    site: str,
    vrf: str,
    cluster_name: str,
    sort_by_vlan_id: bool = True
) -> Optional[Dict[str, Any]]:
    """Atomically find unallocated segment and mark as reserved."""
    ...
```

### Pattern: Direct Python Filtering

Replace `_matches_query` with direct Python comparisons inside `get_segments()`:

```python
# In netbox_segments.py, after fetching prefixes from NetBox and converting:
def _segment_matches(segment: Dict, **filters) -> bool:
    if filters.get("site") and segment.get("site", "").lower() != filters["site"].lower():
        return False
    if filters.get("vrf") and segment.get("vrf", "").lower() != filters["vrf"].lower():
        return False
    if filters.get("vlan_id") is not None and segment.get("vlan_id") != filters["vlan_id"]:
        return False
    if "allocated" in filters:
        is_alloc = bool(segment.get("cluster_name")) and not segment.get("released", False)
        if filters["allocated"] != is_alloc:
            return False
    if filters.get("cluster_name"):
        if segment.get("cluster_name") != filters["cluster_name"]:
            return False
    return True
```

### Anti-Patterns to Avoid

- **Recreating the class wrapper**: `NetBoxStorage` adds no value — don't replace it with another class. Module-level functions are simpler and sufficient.
- **Keeping the MongoDB operators as named constants**: Don't introduce `OP_NE = "$ne"` — remove the operator pattern entirely.
- **Overly splitting the new segment file**: `netbox_segments.py` should contain ALL segment operations (read + write) since they share the same cache and conversion logic.
- **Changing the `src/utils/database/` class structure**: Keep `DatabaseUtils`, `AllocationUtils`, etc. — only replace their internal MongoDB calls with domain calls. The service layer doesn't change.
- **Forgetting to update `src/utils/validators/organization_validators.py`**: It calls `get_storage().get_vrfs()` directly — this needs to become a direct import of `get_vrfs()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Shared cluster regex matching | A new regex engine | `re.search()` inline | Already used elsewhere; one import |
| Text search across fields | A search framework | `re.search()` per field + `any()` | Pattern already present in `_matches_condition`; just inline it |
| Cache invalidation | Any new mechanism | Existing `invalidate_cache(CACHE_KEY_PREFIXES)` calls | Already works; keep as-is |
| Thread safety for cache | Locks, semaphores | Existing inflight-request tracking | Already handles concurrent fetches |

## Common Pitfalls

### Pitfall 1: Breaking the `$regex` Shared-Cluster Logic

**What goes wrong:** The shared-cluster feature stores comma-separated cluster names like `"cluster1,cluster2"`. The `$regex` pattern `(^|,){cluster}(,|$)` matches a cluster name at any position in the comma list. If this is replaced with a simple equality check (`cluster_name == value`), shared-cluster lookup silently breaks.

**Why it happens:** The replacement looks simple but the feature requirement is non-obvious.

**How to avoid:** Keep the regex logic in `AllocationUtils.find_existing_allocation()` and `AllocationUtils.release_segment()`. These callers do the regex themselves — they don't need the MongoDB interpreter to do it. The fix is: call `get_segments(site=site, vrf=vrf)` and apply the regex filter in Python within the utils method.

**Warning signs:** Tests for shared segments fail, or allocation returns wrong results when a cluster is part of a comma-list.

### Pitfall 2: `get_storage()` Creates a New Instance Every Call

**What goes wrong:** Each call to `get_storage()` returns `NetBoxStorage()`, which creates new `NetBoxHelpers`, `NetBoxQueryOps`, `NetBoxCRUDOps` objects. This is fine now because the real singleton is `_netbox_client` at the module level. After refactoring to module-level functions, the same singleton still works. But if someone re-introduces a class with instance state (e.g., a cache inside the class), it will break.

**How to avoid:** Module-level functions share module-level state (`_netbox_client`, `_cache`). Keep state at module level.

### Pitfall 3: Three-Way Tenant Cache Inconsistency

**What goes wrong:** `prefetch_reference_data()` in `netbox_storage.py` pre-caches the tenant under two keys: `CACHE_KEY_REDBULL_TENANT_ID` (the `.id` integer) and `CACHE_KEY_TENANT_REDBULL` (the full object). `get_tenant("RedBull")` in `netbox_helpers.py` checks `get_tenant_cache_key("RedBull")` which resolves to `"tenant_redbull"` — the same string as `CACHE_KEY_TENANT_REDBULL`. These are consistent. But `get_redbull_tenant_id()` checks `CACHE_KEY_REDBULL_TENANT_ID` for the integer, and falls back to calling `get_tenant()` which fetches the full object. This double-caching pattern is fragile.

**How to avoid:** During refactoring, collapse `get_redbull_tenant_id()` — it's a 10-line method that just returns `tenant.id`. Callers that need the tenant ID should call `get_tenant(TENANT_REDBULL)` and access `.id` themselves. The `CACHE_KEY_REDBULL_TENANT_ID` pre-declared cache entry can be removed.

### Pitfall 4: `get_site()` Name Must Change Across All Callers

**What goes wrong:** Renaming `get_site()` to `get_site_group()` requires finding all call sites. Currently only `netbox_crud_ops.py` calls it: `await self.helpers.get_site(document["site"])`. After merging, this becomes an internal call inside `netbox_segments.py` to `get_site_group()` from `netbox_objects.py`.

**How to avoid:** Search for `get_site(` before completing the refactoring.

**Warning signs:** `AttributeError: 'NetBoxHelpers' object has no attribute 'get_site'` if any call site is missed.

### Pitfall 5: `__init__.py` Export List Must Be Updated

**What goes wrong:** The current `__init__.py` exports `NetBoxStorage`, `get_storage`, `init_storage`, `close_storage`. After refactoring, `NetBoxStorage` and `get_storage` no longer exist. Any code importing them will break.

**How to avoid:** Update `__init__.py` to export the new domain functions. Also check `src/utils/validators/organization_validators.py` which imports `get_storage` directly from `src/database/netbox_storage`.

**Warning signs:** `ImportError: cannot import name 'get_storage'` at startup.

### Pitfall 6: `prefix_to_segment` Callers Must Update Signature

**What goes wrong:** `prefix_to_segment(prefix, self.nb)` is called in two places: `netbox_query_ops.py:110` and `netbox_crud_ops.py:176`. After removing the dead `nb_client` parameter, calling `prefix_to_segment(prefix, self.nb)` will fail with `TypeError: takes 1 positional argument but 2 were given`.

**How to avoid:** Remove the parameter from the function signature AND update both call sites simultaneously.

## Code Examples

### Example: Replacing `find_one` + `$set` Pattern

Current pattern in `segment_crud.py`:
```python
# Current (MongoDB API)
storage = get_storage()
result = await storage.update_one(
    {"_id": segment_id},
    {"$set": update_data}
)
```

Target pattern after refactoring:
```python
# Target (domain API, direct import)
from ...database.netbox_segments import update_segment
result = await update_segment(segment_id, update_data)
```

### Example: Replacing `$or` Search Pattern

Current pattern in `segment_queries.py`:
```python
# Current (MongoDB API with $or)
query["$or"] = search_conditions  # search_conditions contains $regex dicts
segments = await storage.find(query)
```

Target pattern after refactoring:
```python
# Target (domain API, Python filtering in search_segments)
all_segments = await get_segments(site=site, allocated=allocated)
results = [s for s in all_segments if _segment_matches_search(s, search_query)]
```

Where `_segment_matches_search` is a plain Python function doing `re.search()` per field.

### Example: Replacing `$regex` Shared-Cluster Match

Current pattern in `allocation_utils.py`:
```python
# Current (MongoDB API)
shared_query_filter = {
    "cluster_name": {"$regex": f"(^|,){cluster_name}(,|$)"},
    "site": site,
    "released": False
}
shared_match = await storage.find_one(shared_query_filter)
```

Target pattern after refactoring:
```python
# Target (domain API, Python regex filter)
import re
segments = await get_segments(site=site, released=False, vrf=vrf)
pattern = re.compile(rf"(^|,){re.escape(cluster_name)}(,|$)")
shared_match = next(
    (s for s in segments if s.get("cluster_name") and pattern.search(s["cluster_name"])),
    None
)
```

## Plan Decomposition Recommendation

This phase has two natural plans:

**Plan 03-01: Refactor `src/database/` module (no caller changes)**
1. Create `netbox_segments.py` — merge crud+query+storage pass-through; domain method signatures; Python-native filtering (replaces the MongoDB interpreter)
2. Create `netbox_objects.py` — copy+rename `netbox_helpers.py`; rename `get_site()` to `get_site_group()`; rename `get_redbull_tenant_id()` to collapse it
3. Update `netbox_utils.py` — remove `nb_client` dead param; absorb 5 functions from `netbox_constants.py`
4. Update `netbox_constants.py` — remove the 5 functions now in utils
5. Update `netbox_client.py` — remove `log_netbox_timing` (33 lines) and `get_netbox_executor` (3 lines)
6. Update `netbox_cache.py` — remove 3 unused pre-declared entries
7. Update `__init__.py` — export new interface
8. Delete `netbox_storage.py`, `netbox_crud_ops.py`, `netbox_query_ops.py`, `netbox_helpers.py`

**Plan 03-02: Update callers in `src/utils/database/` and validators**
1. Update `segment_crud.py` — replace `get_storage().insert_one/find_one/update_one/delete_one` with domain calls
2. Update `allocation_utils.py` — replace `find_one/find_one_and_update/update_one` with domain calls; inline regex for shared-cluster
3. Update `segment_queries.py` — replace `find/find_one` with domain calls; inline `$or`/`$regex`/`$ne` as Python
4. Update `statistics_utils.py` — replace `find` with domain call
5. Update `organization_validators.py` — replace `get_storage().get_vrfs()` with direct import
6. Verify `DatabaseUtils` aggregation class still works

These two plans are sequenced (03-02 depends on 03-01). Each plan can be independently tested by running the API after each step.

## State of the Art

| Old Approach | Current Approach | Impact |
|---|---|---|
| MongoDB query API on non-MongoDB backend | Domain-named module-level functions | Eliminates 65-line interpreter, honest naming |
| Class facade (`NetBoxStorage`) as mediator | Direct function imports | Removes one indirection layer, clearer dependency graph |
| `netbox_helpers.py` doing both reads and writes | `netbox_objects.py` (domain-named) | File purpose matches content |
| Utility functions in constants file | Functions moved to `netbox_utils.py` | Constants file contains only constants |

## Open Questions

1. **`netbox_storage.py` lifecycle functions**
   - What we know: `prefetch_reference_data()`, `init_storage()`, `close_storage()` are the only real logic in `netbox_storage.py`; the `NetBoxStorage` class is pure delegation.
   - What's unclear: Where should these 3 lifecycle functions live in the new structure? Options: (a) stay in a slimmed `netbox_storage.py` with the class removed, or (b) move to `netbox_segments.py` since prefetch is mostly about segments/prefixes.
   - Recommendation: Keep a thin `netbox_storage.py` containing only the 3 lifecycle functions — this preserves the `__init__.py` export of `init_storage`/`close_storage` without changes to importers outside the database module.

2. **`find_one_and_update` atomicity**
   - What we know: The current implementation is not truly atomic — it calls `find()` then `update_one()` as two separate NetBox API calls. The "atomic" claim in the docstring is aspirational.
   - What's unclear: Whether callers rely on this being truly atomic (e.g., under concurrent load).
   - Recommendation: Document the non-atomicity in the new `allocate_segment()` function. Do not attempt to fix it in this phase — it's a behaviour preservation refactor.

3. **`count_documents` usage**
   - What we know: `count_documents` exists on `NetBoxStorage` and is delegated to `NetBoxQueryOps`, but grepping shows it is NOT called from any file in `src/utils/database/` or services. The `statistics_utils.py` uses `storage.find({...})` + `len()` instead.
   - Recommendation: Do not add a `count_segments()` function to the new API. Callers that want a count use `len(get_segments(...))`.

## Sources

### Primary (HIGH confidence)
- Direct source code inspection: all 9 files in `src/database/`, all 5 files in `src/utils/database/`, both services that call `DatabaseUtils`
- grep/search of entire `src/` tree for each dead code claim

### Secondary (MEDIUM confidence)
- None required — this is a pure internal code refactoring with no external library decisions

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Dead code inventory: HIGH — every claim was verified by grep with zero results for the named symbol outside its definition
- File structure: HIGH — direct file reading, confirmed actual line counts
- Caller impact: HIGH — traced every `get_storage()` call site and every MongoDB operator used
- Refactoring plan: HIGH — straightforward mechanical changes with no library upgrades or behaviour changes

**Research date:** 2026-03-28
**Valid until:** Until code changes — this research is based entirely on the current source, not on any external sources that might change
