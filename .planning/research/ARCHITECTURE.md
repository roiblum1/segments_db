# Architecture Patterns

**Domain:** VLAN scoping bug fix -- NetBox VLAN-to-VLAN-Group association
**Researched:** 2026-03-27

## Root Cause Analysis

The bug is in `netbox_helpers.py:get_or_create_vlan()` (line 137-227). When two sites (e.g., Site1, Site2) create the same VLAN ID (e.g., VLAN 48) under the same VRF, they share a single NetBox VLAN object because the lookup uses `vid` alone without scoping to the VLAN Group.

### The Exact Bug (line 155-159)

```python
# Current code -- BROKEN
vlan_filter = {"vid": vlan_id}  # line 155: No group scoping!

vlan = await run_netbox_get(
    lambda: self.nb.ipam.vlans.get(**vlan_filter),  # line 158-159
    f"get VLAN {vlan_id}"
)
```

This finds the FIRST VLAN with that VID globally. If Site1 already created VLAN 48, Site2's request reuses it. The code at lines 197-221 tries to handle the "VLAN exists" case by updating the group, but this makes things worse -- it either reassigns Site1's VLAN to Site2's group, or finds the existing VLAN in the target group (lines 204-214) but leaves the original VLAN orphaned from Site1.

### What Should Happen

Each VLAN Group (e.g., `Network1-ClickCluster-Site1`) is a unique namespace. VLAN 48 in `Network1-ClickCluster-Site1` and VLAN 48 in `Network1-ClickCluster-Site2` must be **two separate NetBox VLAN objects**, each scoped to its respective VLAN Group.

## Recommended Architecture

### Correct Lookup Strategy: Group-first, then VID

The fix must resolve the VLAN Group BEFORE looking up the VLAN, then search by `(group_id, vid)` instead of `(vid)` alone.

### Component Boundaries

| Component | Responsibility | Change Required |
|-----------|---------------|-----------------|
| `netbox_helpers.py` | VLAN lookup + creation | **PRIMARY FIX** -- restructure `get_or_create_vlan()` |
| `netbox_crud_ops.py` | Calls `get_or_create_vlan()` | **No change needed** -- already passes `site` and `vrf` params |
| `netbox_query_ops.py` | Read operations | **No change needed** -- reads prefix data, VLAN association comes from prefix |
| `netbox_cache.py` | Cache management | **Minor change** -- VLAN cache key needs group awareness |
| `netbox_constants.py` | Constants | **No change needed** |
| `netbox_utils.py` | `prefix_to_segment()` conversion | **No change needed** -- reads VLAN from prefix object directly |
| `netbox_storage.py` | Storage facade | **No change needed** |

### Data Flow (Fixed)

```
insert_one() / update_one()
    |
    v
get_or_create_vlan(vlan_id=48, name="EPG_X", site="site1", vrf="Network1")
    |
    v
[1] Resolve VLAN Group: "Network1-ClickCluster-Site1"  (get_or_create_vlan_group)
    |
    v
[2] Lookup VLAN by (group_id + vid):  nb.ipam.vlans.get(group_id=group.id, vid=48)
    |
    +-- Found? Return it (update name if changed)
    |
    +-- Not found? Create VLAN with group=group.id, vid=48, name="EPG_X"
```

## Exact Code Paths That Need Changing

### File 1: `src/database/netbox_helpers.py` -- `get_or_create_vlan()` (lines 137-227)

This is the **only method that needs a structural change**. The fix replaces the current two-phase logic (find globally, then fixup group) with a single-phase group-scoped lookup.

**Current broken flow:**
1. Line 155: `vlan_filter = {"vid": vlan_id}` -- global lookup
2. Line 158: `self.nb.ipam.vlans.get(**vlan_filter)` -- finds first match globally
3. Lines 197-227: Complex "VLAN exists" branch that tries to reassign groups after the fact

**Fixed flow:**
1. Resolve the VLAN Group first (already has `get_or_create_vlan_group()` -- lines 316-362)
2. Look up VLAN by `(group_id, vid)` -- scoped to the correct group
3. If not found, create with `group=group.id` -- correctly scoped from birth
4. If found, update name if needed -- simple, no group shuffling

**Key simplification:** The entire "VLAN exists" branch (lines 197-227) that checks for group conflicts, reassigns VLANs between groups, and handles duplicate detection becomes unnecessary. Each group gets its own VLAN objects. The method becomes roughly half its current size.

**Edge case -- no site/vrf provided:** Lines 137 parameters `site_slug` and `vrf_name` are both `Optional`. When both are `None`, there is no VLAN Group to scope to. This fallback should remain as a global lookup (degenerate case), but in practice `insert_one()` always provides both.

### File 2: `src/database/netbox_helpers.py` -- `cleanup_unused_vlan()` (lines 97-134)

**No structural change needed**, but behavior verification required. This method checks cached prefixes to see if a VLAN is still in use before deleting it. After the fix, VLANs are group-scoped, so a VLAN 48 in Group A is different from VLAN 48 in Group B. The `safe_get_id(vlan_obj)` comparison (line 118) uses the VLAN's internal NetBox ID (not VID), so it correctly distinguishes between two VLAN objects with the same VID. **No change needed.**

### File 3: `src/database/netbox_crud_ops.py` -- `_update_vlan_if_changed()` (lines 182-217)

**No structural change needed.** This method calls `self.helpers.get_or_create_vlan(vlan_id, epg_name, site, vrf)` at line 201. Once the helper is fixed, this call automatically gets the correct group-scoped VLAN. The old VLAN cleanup logic (lines 213-216) compares by VID, which is still correct for determining if the VLAN assignment changed.

### File 4: `src/database/netbox_crud_ops.py` -- `delete_one()` (lines 258-313)

**Behavior review needed.** Currently deletes the VLAN associated with a prefix (lines 295-302). After the fix, each prefix has its own group-scoped VLAN, so deleting the VLAN when deleting the prefix is safe. However, the current code does NOT check if other prefixes in the same group share the VLAN -- it just deletes unconditionally. This was masked before because all sites shared one VLAN object (so `cleanup_unused_vlan` was the safety check). After the fix, this is still correct because each prefix gets its own VLAN within its group. **No change needed, but verify in testing.**

## Cache Impact Analysis

### Current Cache Keys (from `netbox_cache.py`)

| Key | TTL | Impact |
|-----|-----|--------|
| `prefixes` | 600s | **No change** -- prefix cache is fetched as a flat list, filtered in-memory |
| `vlans` | 600s | **Currently unused for lookups** -- only invalidated on delete (line 307). The `get_or_create_vlan()` method does NOT use this cache; it calls `nb.ipam.vlans.get()` directly every time |
| `vlan_group_{name}` | 300s | **No change** -- already keyed by group name (e.g., `vlan_group_Network1-ClickCluster-Site1`) |
| `redbull_tenant_id` | 3600s | No change |
| `vrfs` | 3600s | No change |

### Cache Recommendation

The `get_or_create_vlan()` method currently makes an uncached NetBox API call on every invocation (line 158). After fixing to group-scoped lookup, consider adding a VLAN cache keyed by `(group_id, vid)` to avoid repeated API calls:

```
Cache key: f"vlan_{group_id}_{vid}"
TTL: CACHE_TTL_SHORT (300s) -- same as VLAN groups
Invalidate on: VLAN create, VLAN delete, VLAN update
```

This is an **optimization, not a requirement** for the bug fix. The fix works correctly without it since `get_or_create_vlan()` is only called during write operations (which are infrequent).

## Patterns to Follow

### Pattern 1: Group-First Resolution (Correct)
**What:** Always resolve the VLAN Group before looking up or creating a VLAN.
**When:** Any VLAN operation where site and VRF are known.
**Why:** The VLAN Group is the scoping boundary. Without it, VLANs collide across sites.

```python
# CORRECT: Resolve group first, then lookup within group
async def get_or_create_vlan(self, vlan_id, name, site_slug=None, vrf_name=None):
    if vrf_name and site_slug:
        site_group = site_slug.capitalize()
        vlan_group = await self.get_or_create_vlan_group(vrf_name, site_group)

        # Scoped lookup
        vlan = await run_netbox_get(
            lambda: self.nb.ipam.vlans.get(group_id=vlan_group.id, vid=vlan_id),
            f"get VLAN {vlan_id} in group {vlan_group.name}"
        )
    else:
        # Fallback: global lookup (no site/vrf context)
        vlan = await run_netbox_get(
            lambda: self.nb.ipam.vlans.get(vid=vlan_id),
            f"get VLAN {vlan_id} (global)"
        )

    if vlan:
        # Update name if changed
        if vlan.name != name:
            vlan.name = name
            await run_netbox_write(lambda: vlan.save(), f"update VLAN {vlan_id} name")
        return vlan

    # Create new VLAN (scoped to group if available)
    vlan_data = {"vid": vlan_id, "name": name, "status": STATUS_ACTIVE}
    # ... add tenant, role, group ...
    return await run_netbox_write(
        lambda: self.nb.ipam.vlans.create(**vlan_data),
        f"create VLAN {vlan_id}"
    )
```

### Pattern 2: Lambda Closure Trap (Existing Risk)
**What:** Python lambdas in loops capture the variable reference, not the value.
**When:** Using `run_netbox_get(lambda: self.nb.ipam.vlans.get(group_id=vlan_group.id, vid=vlan_id), ...)`.
**Why:** If `vlan_group` or `vlan_id` are reassigned before the lambda executes in the thread pool, it reads the wrong value.
**Prevention:** The current code already avoids this by not using lambdas in loops. The fix should maintain this pattern.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Global-First Lookup with Post-Hoc Group Assignment
**What:** The current approach -- find a VLAN globally by VID, then try to assign it to the correct group afterward.
**Why bad:** Race conditions between sites. VLAN reassignment from one group to another breaks the first site's association. Creates orphaned VLANs.
**Instead:** Always scope the lookup to the VLAN Group from the start.

### Anti-Pattern 2: Shared VLAN Objects Across Groups
**What:** Reusing a single VLAN object for multiple VLAN Groups because they share the same VID.
**Why bad:** NetBox VLANs can only belong to one VLAN Group. Moving them between groups breaks prefix associations. EPG name changes on one site affect the other.
**Instead:** One VLAN object per (Group, VID) combination. VLAN 48 in Group A and VLAN 48 in Group B are two distinct NetBox objects.

### Anti-Pattern 3: Updating VLAN Group After Prefix Association
**What:** Creating a prefix pointing to VLAN X, then changing VLAN X's group.
**Why bad:** The prefix still points to VLAN X, but if another prefix was also pointing to VLAN X, it now sees the wrong group.
**Instead:** Resolve the correct VLAN (in the correct group) before associating it with the prefix.

## Build Order / Dependency Between Changes

The fix is contained within a single method, but should be implemented in this order to maintain safety:

```
Step 1: Fix get_or_create_vlan() in netbox_helpers.py
        - Change lookup from vid-only to (group_id, vid)
        - Remove the complex "VLAN exists" group-reassignment branch
        - Keep the fallback for when site/vrf are not provided
        Dependencies: None

Step 2: Verify callers pass site and vrf consistently
        - netbox_crud_ops.py:insert_one() line 127-132 -- already passes both
        - netbox_crud_ops.py:_update_vlan_if_changed() line 201 -- already passes both
        Dependencies: Step 1 complete

Step 3: Test with existing NetBox data (backward compatibility)
        - Existing VLANs without groups should still work (fallback path)
        - New VLANs must be created in the correct group
        - Two sites with same VID must get separate VLAN objects
        Dependencies: Steps 1-2 complete

Step 4 (optional): Add VLAN cache by (group_id, vid)
        - Reduces API calls for repeated lookups
        - Not required for correctness
        Dependencies: Step 1 complete
```

## Existing Data Migration Consideration

After deploying the fix, existing VLAN objects in NetBox may be shared across sites (the legacy bug state). The fix handles this gracefully:

- **New segments:** Will create correctly scoped VLANs in the right VLAN Group.
- **Existing segments:** Their VLAN association (prefix.vlan) still points to the shared VLAN object. This works but is not ideal.
- **Migration strategy (optional):** A one-time script could iterate over all prefixes, check if their VLAN is in the correct group, and create new group-scoped VLANs where needed. This is a post-deployment cleanup, not a blocker.

## Scalability Considerations

| Concern | Current (buggy) | After Fix |
|---------|-----------------|-----------|
| VLAN objects per VID | 1 (shared, wrong) | N (one per site, correct) |
| NetBox API calls per segment create | 1 VLAN lookup | 1 VLAN Group lookup (cached) + 1 VLAN lookup |
| VLAN Group cache effectiveness | Good (300s TTL) | Same -- groups are resolved and cached per `get_or_create_vlan_group()` |
| Total VLAN objects in NetBox | Low (shared) | Higher (one per site per VID) -- this is correct behavior |

The fix adds at most one extra cached lookup (VLAN Group resolution) per write operation. Since VLAN Groups are cached with 300s TTL and write operations are infrequent, the performance impact is negligible.

## Sources

- Direct code analysis of `src/database/netbox_helpers.py`, `netbox_crud_ops.py`, `netbox_query_ops.py`, `netbox_cache.py`, `netbox_constants.py`, `netbox_utils.py`, `netbox_storage.py`
- NetBox data model: VLANs belong to exactly one VLAN Group, uniqueness enforced by `(group, vid)` -- HIGH confidence from pynetbox API patterns visible in existing code (line 205: `self.nb.ipam.vlans.get(group_id=vlan_group.id, vid=vlan_id)`)
- Project context from `.planning/PROJECT.md` confirming the bug description and constraints
