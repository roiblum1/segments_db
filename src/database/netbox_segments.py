"""
NetBox Segment Operations

Domain-named module for all segment (prefix) operations.

Merges: netbox_crud_ops.py + netbox_query_ops.py + storage delegation logic.
Exposes module-level async functions — no class wrapper.
Filtering is done via Python-native typed parameters (no MongoDB query interpreter).
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any

from fastapi import HTTPException

from .netbox_objects import NetBoxObjects
from .netbox_client import get_netbox_client, run_netbox_get, run_netbox_write
from .netbox_cache import (
    get_cached,
    set_cache,
    invalidate_cache,
    get_inflight_request,
    set_inflight_request,
    remove_inflight_request,
)
from .netbox_utils import (
    prefix_to_segment,
    safe_get_id,
    safe_get_attr,
    ensure_custom_fields,
    set_custom_field,
)
from .netbox_constants import (
    CACHE_KEY_PREFIXES,
    CACHE_KEY_VLANS,
    CUSTOM_FIELD_DHCP,
    CUSTOM_FIELD_CLUSTER,
    STATUS_ACTIVE,
    STATUS_RESERVED,
    TENANT_REDBULL,
    ROLE_DATA,
    SCOPE_TYPE_SITEGROUP,
)

logger = logging.getLogger(__name__)

# Module-level singletons — wired by init_segments_module()
_nb = None
_objects: Optional[NetBoxObjects] = None


def init_segments_module(nb_client) -> None:
    """Called once from init_storage() to wire the module to the NetBox client."""
    global _nb, _objects
    _nb = nb_client
    _objects = NetBoxObjects(nb_client)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _segment_matches(
    segment: Dict[str, Any],
    site: Optional[str] = None,
    vrf: Optional[str] = None,
    vlan_id: Optional[int] = None,
    allocated: Optional[bool] = None,
    cluster_name: Optional[str] = None,
    released: Optional[bool] = None,
) -> bool:
    """Pure Python filter — replaces the old MongoDB-style query interpreter."""
    if site is not None and segment.get("site", "").lower() != site.lower():
        return False

    if vrf is not None and segment.get("vrf", "").lower() != vrf.lower():
        return False

    if vlan_id is not None and segment.get("vlan_id") != vlan_id:
        return False

    if allocated is True:
        has_cluster = bool(segment.get("cluster_name"))
        is_released = segment.get("released", False)
        if not has_cluster or is_released:
            return False

    if allocated is False:
        if bool(segment.get("cluster_name")):
            return False

    if cluster_name is not None and segment.get("cluster_name") != cluster_name:
        return False

    if released is not None and segment.get("released", False) != released:
        return False

    return True


def _add_associations(prefix_data: Dict[str, Any], vrf_obj, site_group_obj, tenant, role, vlan_obj):
    """Add object associations to prefix_data if they exist."""
    if vrf_obj:
        prefix_data["vrf"] = vrf_obj.id
    if site_group_obj:
        prefix_data["scope_type"] = SCOPE_TYPE_SITEGROUP
        prefix_data["scope_id"] = site_group_obj.id
    if tenant:
        prefix_data["tenant"] = tenant.id
    if role:
        prefix_data["role"] = role.id
    if vlan_obj:
        prefix_data["vlan"] = vlan_obj.id


def _build_custom_fields(document: Dict[str, Any]) -> Dict[str, Any]:
    """Build custom fields dictionary from document."""
    custom_fields = {}
    if "dhcp" in document:
        custom_fields[CUSTOM_FIELD_DHCP] = document["dhcp"]
    if document.get("cluster_name"):
        custom_fields[CUSTOM_FIELD_CLUSTER] = document["cluster_name"]
    return custom_fields


async def _apply_prefix_updates(prefix, updates: Dict[str, Any], segment: Dict[str, Any]):
    """Apply all prefix updates and return old VLAN for cleanup if changed."""
    # Basic field updates
    field_mappings = {
        "description": ("comments", None),
        "segment": ("prefix", None),
    }

    for update_key, (prefix_attr, _) in field_mappings.items():
        if update_key in updates:
            setattr(prefix, prefix_attr, updates[update_key])

    # VRF update
    if "vrf" in updates:
        vrf_obj = await _objects.get_vrf(updates["vrf"])
        if vrf_obj:
            prefix.vrf = vrf_obj.id

    # DHCP custom field
    if "dhcp" in updates:
        set_custom_field(prefix, CUSTOM_FIELD_DHCP, updates["dhcp"])

    # VLAN update
    old_vlan_for_cleanup = None
    if "vlan_id" in updates or "epg_name" in updates:
        old_vlan_for_cleanup = await _update_vlan_if_changed(prefix, updates, segment)

    # Allocation state updates
    if updates.get("cluster_name"):
        prefix.status = STATUS_RESERVED
        set_custom_field(prefix, CUSTOM_FIELD_CLUSTER, updates["cluster_name"])
    elif updates.get("released"):
        prefix.status = STATUS_ACTIVE
        ensure_custom_fields(prefix)
        prefix.custom_fields[CUSTOM_FIELD_CLUSTER] = None

    return old_vlan_for_cleanup


async def _update_vlan_if_changed(prefix, updates: Dict[str, Any], segment: Dict[str, Any]):
    """Update VLAN assignment and cleanup old VLAN if changed."""
    # Get current and new VLAN info
    vlan_id = updates.get("vlan_id", segment.get("vlan_id"))
    epg_name = updates.get("epg_name", segment.get("epg_name"))
    site = updates.get("site", segment.get("site"))
    vrf = updates.get("vrf", segment.get("vrf"))

    # Prepare parallel tasks: fetch old VLAN and create new VLAN
    old_vlan_task = asyncio.sleep(0)
    old_vlan_id = safe_get_id(safe_get_attr(prefix, 'vlan'))
    if old_vlan_id:
        old_vlan_task = run_netbox_get(
            lambda: _nb.ipam.vlans.get(old_vlan_id),
            f"get old VLAN {old_vlan_id}"
        )

    new_vlan_task = asyncio.sleep(0)
    if vlan_id and epg_name:
        new_vlan_task = _objects.get_or_create_vlan(vlan_id, epg_name, site, vrf)

    # Execute in parallel
    old_vlan_obj, new_vlan_obj = await asyncio.gather(
        old_vlan_task, new_vlan_task, return_exceptions=True
    )

    # Update to new VLAN
    if new_vlan_obj and not isinstance(new_vlan_obj, Exception):
        prefix.vlan = new_vlan_obj.id

    # Return old VLAN for cleanup after save
    if old_vlan_obj and not isinstance(old_vlan_obj, Exception):
        old_vlan_vid = old_vlan_obj.vid
        if old_vlan_vid != vlan_id:  # Only return if VLAN actually changed
            return old_vlan_obj
    return None


# ---------------------------------------------------------------------------
# Public domain interface
# ---------------------------------------------------------------------------

async def get_segments(
    site: Optional[str] = None,
    vrf: Optional[str] = None,
    vlan_id: Optional[int] = None,
    allocated: Optional[bool] = None,
    cluster_name: Optional[str] = None,
    released: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Return segments filtered by typed parameters.

    All filtering is done in-memory after fetching from NetBox.
    The tenant filter is applied at the NetBox API level to reduce data volume.
    """
    # Build NetBox filter — always scope to RedBull tenant
    nb_filter: Dict[str, Any] = {}

    tenant = await _objects.get_tenant(TENANT_REDBULL)
    if tenant:
        nb_filter["tenant_id"] = tenant.id

    # vlan_id can be pushed to NetBox API level
    if vlan_id is not None:
        nb_filter["vlan_vid"] = vlan_id

    cache_key = CACHE_KEY_PREFIXES
    prefixes = get_cached(cache_key)

    if prefixes is None:
        inflight_task = get_inflight_request(cache_key)
        if inflight_task:
            try:
                prefixes = await inflight_task
            except Exception as e:
                logger.error(f"In-flight request failed: {e}")
                prefixes = None

        if prefixes is None:
            fetch_future = asyncio.create_task(
                run_netbox_get(
                    lambda: list(_nb.ipam.prefixes.filter(**nb_filter)),
                    "fetch prefixes",
                )
            )
            set_inflight_request(cache_key, fetch_future)
            try:
                prefixes = await fetch_future
                set_cache(cache_key, prefixes)
            finally:
                remove_inflight_request(cache_key)

    # Convert and filter
    segments = []
    for prefix in prefixes:
        segment = prefix_to_segment(prefix)

        # Skip segments missing required fields
        if not segment.get("site") or not segment.get("vrf"):
            continue

        if not _segment_matches(
            segment,
            site=site,
            vrf=vrf,
            vlan_id=vlan_id,
            allocated=allocated,
            cluster_name=cluster_name,
            released=released,
        ):
            continue

        segments.append(segment)

    return segments


async def get_segment_by_id(segment_id: str) -> Optional[Dict[str, Any]]:
    """Return the segment with the given ID, or None."""
    all_segments = await get_segments()
    for segment in all_segments:
        if segment["_id"] == segment_id:
            return segment
    return None


async def create_segment(document: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new segment (prefix) in NetBox."""
    try:
        # Fetch reference data sequentially (all cached lookups except VLAN creation)
        vrf_obj = None
        if document.get("vrf"):
            vrf_obj = await _objects.get_vrf(document["vrf"])

        site_group_obj = None
        if document.get("site"):
            site_group_obj = await _objects.get_site_group(document["site"])

        tenant = await _objects.get_tenant(TENANT_REDBULL)
        role = await _objects.get_role(ROLE_DATA, "prefix")

        # VLAN creation (may need NetBox write)
        vlan_obj = None
        if document.get("vlan_id"):
            vlan_obj = await _objects.get_or_create_vlan(
                document["vlan_id"],
                document.get("epg_name", f"VLAN_{document['vlan_id']}"),
                document.get("site"),
                document.get("vrf"),
            )

        # Build prefix data with all associations
        prefix_data = {
            "prefix": document["segment"],
            "description": "",  # Empty initially, will show cluster name when allocated
            "comments": document.get("description", ""),  # User info goes in comments
            "status": STATUS_ACTIVE,
            "is_pool": True,  # All IP addresses within this prefix are considered usable
        }

        # Add object associations (only if they exist)
        _add_associations(prefix_data, vrf_obj, site_group_obj, tenant, role, vlan_obj)

        # Add custom fields
        custom_fields = _build_custom_fields(document)
        if custom_fields:
            prefix_data["custom_fields"] = custom_fields

        # Create prefix in NetBox
        try:
            prefix = await run_netbox_write(
                lambda: _nb.ipam.prefixes.create(**prefix_data),
                f"create prefix {prefix_data['prefix']}",
            )
        except Exception as create_error:
            error_msg = str(create_error)
            if "Unknown field name" in error_msg or "custom field" in error_msg.lower():
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Custom fields '{CUSTOM_FIELD_DHCP}' and '{CUSTOM_FIELD_CLUSTER}' are required but not found in NetBox. "
                        "Please run the initialization script to create them: python3 create_netbox_resources.py"
                    ),
                )
            raise

        logger.info(f"Created prefix in NetBox: {prefix.prefix} (ID: {prefix.id})")
        logger.debug(f"Created prefix with VRF={document.get('vrf')}, DHCP={document.get('dhcp')}, is_pool=True")

        # Invalidate cache since we modified data
        invalidate_cache(CACHE_KEY_PREFIXES)

        return prefix_to_segment(prefix)

    except Exception as e:
        logger.error(f"Error creating prefix in NetBox: {e}", exc_info=True)
        raise


async def update_segment(segment_id: str, updates: Dict[str, Any]) -> bool:
    """Update a segment in NetBox.

    Args:
        segment_id: The segment's _id string (NetBox prefix ID).
        updates: Dict of fields to update (no $set wrapper needed).
    """
    segment = await get_segment_by_id(segment_id)
    if not segment:
        return False

    try:
        prefix_id = segment["_id"]

        # Get prefix object
        prefix = await run_netbox_get(
            lambda: _nb.ipam.prefixes.get(prefix_id),
            f"get prefix {prefix_id}",
        )

        old_vlan_for_cleanup = await _apply_prefix_updates(prefix, updates, segment)

        # Save changes FIRST before cleanup
        await run_netbox_write(
            lambda: prefix.save(),
            f"save prefix {prefix_id}",
        )

        # Clean up old VLAN if it was returned (AFTER save so NetBox sees the change)
        if old_vlan_for_cleanup:
            await _objects.cleanup_unused_vlan(old_vlan_for_cleanup)

        # Invalidate cache since we modified data
        invalidate_cache(CACHE_KEY_PREFIXES)

        return True

    except Exception as e:
        logger.error(f"Error updating prefix in NetBox (id: {segment_id}, updates: {updates}): {e}", exc_info=True)
        return False


async def delete_segment(segment_id: str) -> bool:
    """Delete a segment from NetBox (prefix and associated VLAN, but not VLAN Group)."""
    segment = await get_segment_by_id(segment_id)
    if not segment:
        return False

    try:
        prefix_id = segment["_id"]

        # Get the prefix object to check for associated VLAN
        prefix = await run_netbox_get(
            lambda: _nb.ipam.prefixes.get(prefix_id),
            f"get prefix {prefix_id} for deletion",
        )

        if not prefix:
            logger.warning(f"Prefix ID {prefix_id} not found in NetBox")
            return False

        # Store VLAN info before deleting prefix (needed for VLAN deletion after prefix is gone)
        vlan_obj = None
        vlan_id = safe_get_id(safe_get_attr(prefix, 'vlan'))
        if vlan_id:
            try:
                vlan_obj = await run_netbox_get(
                    lambda: _nb.ipam.vlans.get(vlan_id),
                    f"get VLAN {vlan_id} for deletion",
                )
            except Exception as e:
                logger.warning(f"Error getting VLAN info for prefix {prefix_id}: {e}", exc_info=True)

        # Delete the prefix FIRST (this removes the dependency on the VLAN)
        await run_netbox_write(
            lambda: prefix.delete(),
            f"delete prefix {prefix_id}",
        )

        # NOW delete the VLAN (prefix is gone, so no dependency conflict)
        if vlan_obj:
            try:
                await run_netbox_write(
                    lambda: vlan_obj.delete(),
                    f"delete VLAN {safe_get_attr(vlan_obj, 'vid', vlan_id)}",
                )
            except Exception as e:
                logger.warning(f"Error deleting VLAN {safe_get_attr(vlan_obj, 'vid', vlan_id)} after prefix deletion: {e}", exc_info=True)
                # Don't fail the whole operation if VLAN deletion fails

        # Invalidate cache since we modified data
        invalidate_cache(CACHE_KEY_PREFIXES)
        invalidate_cache(CACHE_KEY_VLANS)

        return True

    except Exception as e:
        logger.error(f"Error deleting prefix from NetBox (id: {segment_id}): {e}", exc_info=True)
        return False


async def allocate_segment(
    site: str,
    vrf: str,
    cluster_name: str,
    sort_by_vlan_id: bool = True,
) -> Optional[Dict[str, Any]]:
    """Find an unallocated segment and allocate it to cluster_name.

    NOTE: This is not truly atomic — find and update are two separate NetBox API
    calls. Under concurrent load, two callers may allocate the same segment.
    Fixing atomicity is out of scope for this refactor.

    Args:
        site: Site slug to filter by.
        vrf: VRF name to filter by.
        cluster_name: Cluster name to assign the segment to.
        sort_by_vlan_id: If True, pick the segment with the lowest VLAN ID first.

    Returns:
        The freshly-fetched allocated segment, or None if no candidates.
    """
    candidates = await get_segments(site=site, vrf=vrf, allocated=False)
    if not candidates:
        return None

    if sort_by_vlan_id:
        candidates.sort(key=lambda s: s.get("vlan_id") or 0)

    segment = candidates[0]

    updates = {
        "cluster_name": cluster_name,
    }
    success = await update_segment(segment["_id"], updates)
    if not success:
        logger.error(f"allocate_segment: update failed for segment {segment['_id']}")
        return None

    # Return fresh data to ensure consistency
    return await get_segment_by_id(segment["_id"])


async def get_vrfs() -> List[str]:
    """Return list of available VRF names."""
    return await _objects.get_vrfs()
