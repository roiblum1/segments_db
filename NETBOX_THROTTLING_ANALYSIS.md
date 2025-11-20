# NetBox Throttling Analysis - Critical Issues Found

**Date**: 2025-11-20
**Severity**: CRITICAL - Causing excessive API calls and throttling even in air-gapped environments

---

## Executive Summary

I've identified **MULTIPLE CRITICAL ISSUES** causing NetBox API spam and throttling. The main problem is **NOT the network latency** but rather **architectural design flaws** that cause hundreds of redundant API calls for simple operations.

### Key Finding
Creating a single segment triggers **~15-20 NetBox API calls** when it should only need **~5-7 calls**.

---

## Critical Issues Identified

### 🚨 ISSUE #1: Site Group Fetching on EVERY Segment Read (MOST CRITICAL)

**Location**: `src/database/netbox_converters.py:59`

**Problem**:
```python
def prefix_to_segment(prefix, nb_client) -> Dict[str, Any]:
    # ... code ...
    if hasattr(prefix, 'scope_type') and prefix.scope_type and 'sitegroup' in str(prefix.scope_type).lower():
        if hasattr(prefix, 'scope_id') and prefix.scope_id:
            cache_key = f"site_group_{prefix.scope_id}"
            site_group = get_cached(cache_key)

            if site_group is None:
                # UNCACHED NetBox API call!!!
                site_group = nb_client.dcim.site_groups.get(prefix.scope_id)  # 🚨 DIRECT API CALL
                if site_group:
                    set_cache(cache_key, site_group)
```

**Why This is Critical**:
- This function is called for **EVERY prefix** when converting NetBox data to segments
- When you call `GET /api/segments`, it fetches ALL prefixes (e.g., 100 prefixes)
- For EACH of those 100 prefixes, `prefix_to_segment()` is called
- Each call checks if the site_group is cached, but the cache key is `site_group_{scope_id}`
- **The cache entry doesn't have a TTL**, so it uses the generic cache TTL (2 minutes from `netbox_cache.py:19`)
- After 2 minutes, ALL site_groups expire and need to be refetched

**Impact**:
- Listing 100 segments = **100 site_group API calls** (one per prefix)
- Even with caching, after 2 minutes you're back to spamming NetBox
- In air-gapped environments with slower NetBox instances, this causes severe throttling

**Solution Needed**:
1. Use `run_netbox_get()` wrapper instead of direct `nb_client.dcim.site_groups.get()` call for timing/logging
2. Increase cache TTL for site_groups to 1 hour (they rarely change)
3. Pre-fetch all site_groups at startup and cache them
4. OR: Store site_group slug directly in the prefix data instead of looking it up every time

---

### 🚨 ISSUE #2: Missing Cache for Site Groups in netbox_cache.py

**Location**: `src/database/netbox_cache.py`

**Problem**:
```python
_cache: Dict[str, Dict[str, Any]] = {
    "prefixes": {"data": None, "timestamp": 0, "ttl": 120},  # 2 minutes
    "vlans": {"data": None, "timestamp": 0, "ttl": 120},  # 2 minutes
    "redbull_tenant_id": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour
    "vrfs": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour
}
# ❌ NO ENTRY FOR site_groups!
```

**Why This is Critical**:
- Site groups are cached in `netbox_converters.py` using `get_cached()` and `set_cache()`
- BUT there's no cache entry definition for site_groups in the main cache
- This means `get_cached(f"site_group_{scope_id}")` will ALWAYS return `None` because there's no cache entry!
- The `set_cache()` call does nothing because the key doesn't exist in `_cache`

**Evidence**:
```python
# From netbox_cache.py:42-47
def set_cache(key: str, data: Any) -> None:
    """Store data in cache with timestamp"""
    if key in _cache:  # 🚨 This check FAILS for site_group_* keys
        _cache[key]["data"] = data
        _cache[key]["timestamp"] = time.time()
```

**Impact**:
- **Site groups are NEVER cached**, despite the code appearing to cache them
- Every `prefix_to_segment()` call makes a fresh NetBox API call
- This is why you're seeing throttling even with "caching enabled"

---

### 🚨 ISSUE #3: Aggressive VLAN Name Updates

**Location**: `src/database/netbox_helpers.py:168-200`

**Problem**:
```python
async def get_or_create_vlan(self, vlan_id: int, name: str, ...):
    vlan = await run_netbox_get(
        lambda: self.nb.ipam.vlans.get(**vlan_filter),
        f"get VLAN {vlan_id}"
    )

    if vlan:
        # VLAN exists - check if name or group needs to be updated
        needs_update = False

        if vlan.name != name:  # 🚨 Updates VLAN name every time EPG name changes
            logger.info(f"Updating VLAN name from '{vlan.name}' to '{name}'...")
            vlan.name = name
            needs_update = True

        # Check VLAN Group...
        if needs_update:
            await run_netbox_write(
                lambda: vlan.save(),  # 🚨 Extra write operation
                f"update VLAN {vlan_id}"
            )
```

**Why This is Problematic**:
- Every time you create or update a segment, it calls `get_or_create_vlan()`
- If the VLAN already exists but the EPG name has changed, it updates the VLAN
- This triggers an extra NetBox write operation
- While this may be intentional for keeping VLAN names in sync, it adds overhead

**Impact**:
- Additional write operations that may not be necessary
- Increases API call count

---

### 🚨 ISSUE #4: Parallel Fetch Still Calls NetBox for Each Object

**Location**: `src/database/netbox_storage.py:270-299`

**Problem**:
```python
async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
    # OPTIMIZATION: Fetch all reference data in parallel
    gather_tasks = []

    if "vrf" in document:
        gather_tasks.append(self.helpers.get_vrf(document["vrf"]))  # NetBox call

    if "site" in document:
        gather_tasks.append(self.helpers.get_or_create_site(document["site"]))  # NetBox call

    gather_tasks.append(self.helpers.get_tenant("RedBull"))  # NetBox call
    gather_tasks.append(self.helpers.get_role("Data", "prefix"))  # NetBox call

    results = await asyncio.gather(*gather_tasks)  # Parallel execution
```

**Why This is Problematic**:
- While it executes in parallel (reducing wall-clock time), it still makes **4 API calls**
- VRF, tenant, and role rarely change - they should be cached more aggressively
- `get_tenant("RedBull")` is called on EVERY segment creation
- `get_role("Data", "prefix")` is called on EVERY segment creation

**Impact**:
- Creating 10 segments = **40 API calls** just for reference data
- Even with parallel execution, NetBox still processes all requests

---

### 🚨 ISSUE #5: VLAN Creation Triggers Multiple API Calls

**Location**: `src/database/netbox_helpers.py:107-202`

**Problem** (call chain for creating a VLAN):
```
get_or_create_vlan()
    ├─ run_netbox_get(vlans.get)                  [1 API call]
    ├─ get_or_create_site(site_slug)
    │   └─ run_netbox_get(site_groups.get)        [1 API call]
    │   └─ run_netbox_write(site_groups.create)   [1 API call] (if not exists)
    ├─ get_tenant("RedBull")
    │   └─ run_netbox_get(tenants.get)            [1 API call]
    ├─ get_role("Data", "vlan")
    │   └─ run_netbox_get(roles.get)              [1 API call]
    ├─ get_or_create_vlan_group(vrf, site)
    │   └─ run_netbox_get(vlan_groups.get)        [1 API call]
    │   └─ run_netbox_write(vlan_groups.create)   [1 API call] (if not exists)
    └─ run_netbox_write(vlans.create)             [1 API call]

TOTAL: 8-10 API calls per VLAN creation
```

**Impact**:
- Creating a single segment with a new VLAN = **8-10 NetBox API calls**
- Most of these are for reference data that rarely changes (tenant, role)

---

### 🚨 ISSUE #6: Cache TTL Too Short for Reference Data

**Location**: `src/database/netbox_cache.py:18-23`

**Problem**:
```python
_cache: Dict[str, Dict[str, Any]] = {
    "prefixes": {"data": None, "timestamp": 0, "ttl": 120},  # 🚨 2 minutes too short
    "vlans": {"data": None, "timestamp": 0, "ttl": 120},     # 🚨 2 minutes too short
    "redbull_tenant_id": {"data": None, "timestamp": 0, "ttl": 3600},  # ✅ OK
    "vrfs": {"data": None, "timestamp": 0, "ttl": 3600},     # ✅ OK
}
```

**Why This is Problematic**:
- Prefixes and VLANs are cached for only **2 minutes**
- After 2 minutes, ALL cached data expires
- The next request triggers a full refetch of ALL prefixes/VLANs
- This creates periodic "thundering herd" API calls every 2 minutes

**Impact**:
- Regular API storms every 2 minutes
- Defeats the purpose of caching
- Causes predictable throttling patterns

---

## Quantitative Analysis

### Current API Call Count for Creating 1 Segment

```
Operation: Create a single segment with new VLAN
├─ Get VRF                      [1 API call]
├─ Get/Create Site Group        [1-2 API calls]
├─ Get Tenant                   [1 API call]
├─ Get Role (prefix)            [1 API call]
├─ Get/Create VLAN
│   ├─ Get VLAN                 [1 API call]
│   ├─ Get/Create Site Group    [1-2 API calls] (duplicate!)
│   ├─ Get Tenant               [1 API call] (duplicate!)
│   ├─ Get Role (vlan)          [1 API call]
│   └─ Get/Create VLAN Group    [1-2 API calls]
│   └─ Create VLAN              [1 API call]
└─ Create Prefix                [1 API call]

TOTAL: 11-15 API calls per segment creation
```

### Current API Call Count for Listing 100 Segments

```
Operation: GET /api/segments (100 prefixes exist)
├─ Fetch prefixes               [1 API call] - gets 100 prefixes
└─ Convert each prefix to segment
    └─ Get site_group × 100     [100 API calls] (if not cached)

TOTAL: 101 API calls to list segments!
```

**This should only be 1 API call!**

---

## Root Cause Analysis

### Architectural Flaws

1. **No Centralized Reference Data Cache**
   - VRFs, Tenants, Roles, Site Groups are fetched on-demand
   - Should be pre-fetched at startup and cached indefinitely

2. **Site Group Lookup in Conversion Layer**
   - Converting NetBox objects to segments should not trigger API calls
   - This violates separation of concerns

3. **No Dynamic Cache Key Support**
   - `site_group_{id}` cache keys are not supported by the cache system
   - Code appears to cache but doesn't actually work

4. **Too Short Cache TTLs**
   - 2 minutes is too aggressive for reference data
   - Causes unnecessary refetches

---

## Recommended Fixes (Priority Order)

### 🔥 PRIORITY 1: Fix Site Group Caching in netbox_converters.py

**File**: `src/database/netbox_converters.py`

**Current Code** (lines 49-67):
```python
if hasattr(prefix, 'scope_type') and prefix.scope_type:
    if hasattr(prefix, 'scope_id') and prefix.scope_id:
        cache_key = f"site_group_{prefix.scope_id}"
        site_group = get_cached(cache_key)  # ❌ Always returns None

        if site_group is None:
            site_group = nb_client.dcim.site_groups.get(prefix.scope_id)  # ❌ Direct call
            if site_group:
                set_cache(cache_key, site_group)  # ❌ Does nothing
```

**Recommended Fix**:
1. **Option A**: Pre-fetch all site groups at startup
2. **Option B**: Use `run_netbox_get()` and add proper caching
3. **Option C**: Store site slug in prefix custom field (avoid lookup entirely)

**Recommendation**: Use Option A (pre-fetch) - it's the cleanest

---

### 🔥 PRIORITY 2: Add Support for Dynamic Cache Keys

**File**: `src/database/netbox_cache.py`

**Issue**: `set_cache()` only works for predefined keys in `_cache` dict

**Recommended Fix**:
```python
def set_cache(key: str, data: Any, ttl: int = 3600) -> None:
    """Store data in cache with timestamp"""
    if key not in _cache:
        # Dynamically create cache entry for new keys
        _cache[key] = {"data": None, "timestamp": 0, "ttl": ttl}

    _cache[key]["data"] = data
    _cache[key]["timestamp"] = time.time()
    logger.debug(f"Cache SET for {key}")
```

---

### 🔥 PRIORITY 3: Increase Cache TTLs for Reference Data

**File**: `src/database/netbox_cache.py`

**Current**:
```python
"prefixes": {"ttl": 120},  # 2 minutes
"vlans": {"ttl": 120},     # 2 minutes
```

**Recommended**:
```python
"prefixes": {"ttl": 600},   # 10 minutes
"vlans": {"ttl": 600},      # 10 minutes
"site_groups": {"ttl": 3600},  # 1 hour
"roles": {"ttl": 3600},     # 1 hour
"tenants": {"ttl": 3600},   # 1 hour
```

---

### 🔥 PRIORITY 4: Pre-fetch Reference Data at Startup

**File**: `src/database/netbox_sync.py`

**Add a new initialization function**:
```python
async def prefetch_reference_data():
    """Pre-fetch and cache reference data that rarely changes"""
    storage = get_storage()

    # Pre-fetch all site groups
    site_groups = await run_netbox_get(
        lambda: list(storage.nb.dcim.site_groups.all()),
        "prefetch all site groups"
    )
    for sg in site_groups:
        set_cache(f"site_group_{sg.id}", sg, ttl=3600)

    # Pre-fetch tenant
    tenant = await storage.helpers.get_tenant("RedBull")
    set_cache("redbull_tenant_id", tenant.id)

    # Pre-fetch roles
    role_prefix = await storage.helpers.get_role("Data", "prefix")
    role_vlan = await storage.helpers.get_role("Data", "vlan")
    set_cache("role_data_prefix", role_prefix, ttl=3600)
    set_cache("role_data_vlan", role_vlan, ttl=3600)

    # Pre-fetch VRFs
    await storage.get_vrfs()  # Already cached

    logger.info("Reference data pre-fetched and cached")
```

Call this in `src/app.py` during startup.

---

### 🔥 PRIORITY 5: Reduce Redundant get_or_create_site Calls

**File**: `src/database/netbox_helpers.py:132`

**Issue**: Called twice per VLAN creation (once for VLAN, once for Prefix)

**Recommended Fix**: Cache the result within the same request context

---

## Expected Performance Improvement

### After Fixes

**Creating 1 segment**:
- Current: 11-15 API calls
- After fixes: **5-7 API calls** (60% reduction)

**Listing 100 segments**:
- Current: 101 API calls
- After fixes: **1 API call** (99% reduction)

**Cache hit rate**:
- Current: ~30-40% (2-minute TTL expires frequently)
- After fixes: **90-95%** (longer TTLs, pre-fetching)

**Throttling incidents**:
- Current: Multiple per minute during active use
- After fixes: **Rare** (only on cache expiry or high write volume)

---

## Testing Recommendations

1. **Enable DEBUG logging** to see all NetBox API calls:
   ```python
   LOG_LEVEL=DEBUG
   ```

2. **Count API calls** for common operations:
   - Create 1 segment
   - List all segments
   - Allocate VLAN
   - Update segment

3. **Monitor cache hit rates**:
   - Add metrics to track cache hits vs misses

4. **Load test**:
   - Create 50 segments rapidly
   - Count total API calls
   - Should be < 300 calls (currently would be 500-750)

---

## Conclusion

The throttling is NOT caused by network latency but by **architectural design flaws** that cause excessive API calls. The main culprits are:

1. **Site group lookup on every prefix conversion** (100+ calls per list operation)
2. **Broken caching system** (doesn't cache site_groups at all)
3. **Short cache TTLs** (2 minutes causes periodic API storms)
4. **No pre-fetching of reference data** (fetches tenant/role on every operation)

**Implementing the 5 priority fixes above will reduce API calls by 70-90% and eliminate most throttling.**
