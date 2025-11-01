# Fix: EPG Name Update Issue

## Problem

When trying to update a segment's EPG name (keeping the same VLAN ID) from the website, the update appeared to succeed but the EPG name didn't actually change in NetBox.

**Example**:
- Original: `SITE3_EPG` with VLAN 1012
- Updated to: `SITE3_EPG1` with VLAN 1012
- Result: EPG name remained `SITE3_EPG` ❌

## Root Cause

The issue was in the `_get_or_create_vlan()` function in [src/database/netbox_storage.py](src/database/netbox_storage.py):

```python
async def _get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None):
    # Search for existing VLAN by ID and site
    vlan = await loop.run_in_executor(
        None,
        lambda: self.nb.ipam.vlans.get(**vlan_filter)
    )

    if not vlan:
        # Create new VLAN
        vlan = await loop.run_in_executor(
            None,
            lambda: self.nb.ipam.vlans.create(**vlan_data)
        )
        logger.info(f"Created VLAN in NetBox: {vlan_id} ({name})")

    return vlan  # ❌ BUG: Returns existing VLAN without updating name
```

**The Problem**:
1. When updating EPG name, the function looks up VLAN by `vlan_id` (e.g., 1012)
2. If VLAN exists, it **returns the existing VLAN object as-is**
3. The VLAN's `name` field (which stores the EPG name) is **never updated**
4. Only the prefix is updated to reference the VLAN, but the VLAN name stays the same

## Solution

Added logic to update the VLAN name if it changed:

```python
async def _get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None):
    # Search for existing VLAN
    vlan = await loop.run_in_executor(
        None,
        lambda: self.nb.ipam.vlans.get(**vlan_filter)
    )

    if not vlan:
        # Create new VLAN
        vlan = await loop.run_in_executor(
            None,
            lambda: self.nb.ipam.vlans.create(**vlan_data)
        )
        logger.info(f"Created VLAN in NetBox: {vlan_id} ({name})")
    else:
        # ✅ FIX: Check if VLAN name needs to be updated
        if vlan.name != name:
            logger.info(f"Updating VLAN name from '{vlan.name}' to '{name}' for VLAN ID {vlan_id}")
            vlan.name = name
            await loop.run_in_executor(None, vlan.save)
            logger.info(f"Updated VLAN name to '{name}' for VLAN ID {vlan_id}")

    return vlan
```

**Changes Made**:
1. Check if the existing VLAN's name differs from the requested name
2. If different, update the VLAN's `name` field
3. Save the VLAN object to persist changes to NetBox
4. Log the update for visibility

## File Modified

**File**: [src/database/netbox_storage.py](src/database/netbox_storage.py)
**Lines**: 659-666 (added 7 lines)
**Function**: `_get_or_create_vlan()`

## Testing

Created comprehensive tests in [test_epg_name_update.py](test_epg_name_update.py):

### Test 1: Single EPG Name Update
- Creates segment with EPG name `TEST_EPG_ORIG_*`
- Updates to `TEST_EPG_UPDATED_*` (same VLAN ID)
- Verifies EPG name changed in NetBox
- **Result**: ✅ PASS

### Test 2: Multiple Consecutive Updates
- Creates segment with EPG name `TEST_MULTI_V1`
- Updates to `TEST_MULTI_V2`, then `TEST_MULTI_V3`, then `TEST_MULTI_FINAL`
- Verifies each update persists correctly
- **Result**: ✅ PASS

### Manual Testing

```bash
# Before fix
$ curl -X PUT .../api/segments/85 -d '{"epg_name":"SITE3_EPG1",...}'
{"message": "Segment updated successfully"}

$ curl .../api/segments/85 | grep epg_name
"epg_name": "SITE3_EPG"  # ❌ Not updated

# After fix
$ curl -X PUT .../api/segments/85 -d '{"epg_name":"SITE3_EPG_UPDATED",...}'
{"message": "Segment updated successfully"}

$ curl .../api/segments/85 | grep epg_name
"epg_name": "SITE3_EPG_UPDATED"  # ✅ Updated correctly
```

## Log Output

Successful update now shows in logs:

```
2025-11-01 16:21:23,743 - INFO - Updating VLAN name from 'SITE3_EPG' to 'SITE3_EPG1' for VLAN ID 1012
2025-11-01 16:21:23,926 - INFO - Updated VLAN name to 'SITE3_EPG1' for VLAN ID 1012
2025-11-01 16:21:23,926 - INFO - Updated prefix 193.168.110.0/24 (ID: 85)
```

## Impact

This fix enables users to:
- ✅ Rename EPG names while keeping the same VLAN ID
- ✅ Update EPG names multiple times
- ✅ Correct EPG naming mistakes without recreating segments
- ✅ Refactor EPG naming conventions across the network

## Server Status

- **Status**: ✅ Running with fix applied
- **URL**: http://localhost:8000
- **NetBox**: https://srcc3192.cloud.netboxapp.com/ (v4.4.2)
- **Process**: `.venv/bin/python main.py`

## Verification Steps

To verify the fix is working:

1. **Via API**:
   ```bash
   # Update EPG name
   curl -X PUT http://localhost:8000/api/segments/{id} \
     -H "Content-Type: application/json" \
     -d '{"site":"site1","vlan_id":100,"epg_name":"NEW_NAME",...}'

   # Verify update
   curl http://localhost:8000/api/segments/{id} | grep epg_name
   ```

2. **Via Website**:
   - Edit a segment
   - Change only the EPG name field
   - Click Save
   - Refresh or view the segment
   - EPG name should show the new value ✅

3. **Via Logs**:
   ```bash
   tail -f /tmp/vlan-manager-app.log | grep "Updating VLAN name"
   ```

## Related Files

- **Fix**: [src/database/netbox_storage.py](src/database/netbox_storage.py) lines 659-666
- **Tests**: [test_epg_name_update.py](test_epg_name_update.py)
- **This Document**: [FIX_EPG_NAME_UPDATE.md](FIX_EPG_NAME_UPDATE.md)

---

**Fixed**: 2025-11-01
**Issue**: EPG name updates not persisting to NetBox
**Status**: ✅ Resolved and tested
