"""
NetBox CRUD Operations

This module handles all write operations for NetBox storage:
- Creating segments (insert_one)
- Updating segments (update_one, find_one_and_update)
- Deleting segments (delete_one)

Separated from query operations for better maintainability.
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from .netbox_client import run_netbox_get, run_netbox_write
from .netbox_cache import invalidate_cache
from .netbox_helpers import NetBoxHelpers
from .netbox_utils import safe_get_id, safe_get_attr, ensure_custom_fields, set_custom_field, prefix_to_segment
from .netbox_constants import (
    CUSTOM_FIELD_DHCP, CUSTOM_FIELD_CLUSTER, STATUS_ACTIVE, STATUS_RESERVED,
    TENANT_REDBULL, ROLE_DATA, SCOPE_TYPE_SITEGROUP,
    CACHE_KEY_PREFIXES, CACHE_KEY_VLANS
)

logger = logging.getLogger(__name__)


class NetBoxCRUDOps:
    """
    NetBox CRUD Operations

    Handles all write operations:
    - insert_one(): Create new segment
    - update_one(): Update existing segment
    - delete_one(): Delete segment
    - find_one_and_update(): Atomic find + update
    """

    def __init__(self, nb_client, helpers: NetBoxHelpers, query_ops):
        self.nb = nb_client
        self.helpers = helpers
        self.query_ops = query_ops

    def _add_associations(self, prefix_data: Dict[str, Any], vrf_obj, site_group_obj, tenant, role, vlan_obj):
        """Add object associations to prefix_data if they exist"""
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

    def _build_custom_fields(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Build custom fields dictionary from document"""
        custom_fields = {}
        if "dhcp" in document:
            custom_fields[CUSTOM_FIELD_DHCP] = document["dhcp"]
        if document.get("cluster_name"):
            custom_fields[CUSTOM_FIELD_CLUSTER] = document["cluster_name"]
        return custom_fields

    async def _apply_prefix_updates(self, prefix, updates: Dict[str, Any], segment: Dict[str, Any]):
        """Apply all prefix updates and return old VLAN for cleanup if changed"""
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
            vrf_obj = await self.helpers.get_vrf(updates["vrf"])
            if vrf_obj:
                prefix.vrf = vrf_obj.id

        # DHCP custom field
        if "dhcp" in updates:
            set_custom_field(prefix, CUSTOM_FIELD_DHCP, updates["dhcp"])

        # VLAN update
        old_vlan_for_cleanup = None
        if "vlan_id" in updates or "epg_name" in updates:
            old_vlan_for_cleanup = await self._update_vlan_if_changed(prefix, updates, segment)

        # Allocation state updates
        if updates.get("cluster_name"):
            prefix.status = STATUS_RESERVED
            set_custom_field(prefix, CUSTOM_FIELD_CLUSTER, updates["cluster_name"])
        elif updates.get("released"):
            prefix.status = STATUS_ACTIVE
            ensure_custom_fields(prefix)
            prefix.custom_fields[CUSTOM_FIELD_CLUSTER] = None

        return old_vlan_for_cleanup

    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new segment in NetBox"""
        try:

            # Fetch reference data sequentially (all cached lookups except VLAN creation)
            # VRF, Site, Tenant, Role are all cached (3600s TTL) - lookups are instant
            vrf_obj = None
            if document.get("vrf"):
                vrf_obj = await self.helpers.get_vrf(document["vrf"])

            site_group_obj = None
            if document.get("site"):
                site_group_obj = await self.helpers.get_site(document["site"])

            tenant = await self.helpers.get_tenant(TENANT_REDBULL)
            role = await self.helpers.get_role(ROLE_DATA, "prefix")

            # VLAN creation (may need NetBox write)
            vlan_obj = None
            if document.get("vlan_id"):
                vlan_obj = await self.helpers.get_or_create_vlan(
                    document["vlan_id"],
                    document.get("epg_name", f"VLAN_{document['vlan_id']}"),
                    document.get("site"),
                    document.get("vrf")
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
            self._add_associations(prefix_data, vrf_obj, site_group_obj, tenant, role, vlan_obj)
            
            # Add custom fields
            custom_fields = self._build_custom_fields(document)
            if custom_fields:
                prefix_data["custom_fields"] = custom_fields

            # Create prefix in NetBox
            try:
                prefix = await run_netbox_write(
                    lambda: self.nb.ipam.prefixes.create(**prefix_data),
                    f"create prefix {prefix_data['prefix']}"
                )
            except Exception as create_error:
                error_msg = str(create_error)
                if "Unknown field name" in error_msg or "custom field" in error_msg.lower():
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            f"Custom fields '{CUSTOM_FIELD_DHCP}' and '{CUSTOM_FIELD_CLUSTER}' are required but not found in NetBox. "
                            "Please run the initialization script to create them: python3 create_netbox_resources.py"
                        )
                    )
                raise

            logger.info(f"Created prefix in NetBox: {prefix.prefix} (ID: {prefix.id})")
            logger.debug(f"Created prefix with VRF={document.get('vrf')}, DHCP={document.get('dhcp')}, is_pool=True")

            # Invalidate cache since we modified data
            invalidate_cache(CACHE_KEY_PREFIXES)

            # Return in our format
            return prefix_to_segment(prefix, self.nb)

        except Exception as e:
            logger.error(f"Error creating prefix in NetBox: {e}", exc_info=True)
            raise

    async def _update_vlan_if_changed(self, prefix, updates: Dict[str, Any], segment: Dict[str, Any]):
        """Update VLAN assignment and cleanup old VLAN if changed"""
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
                lambda: self.nb.ipam.vlans.get(old_vlan_id),
                f"get old VLAN {old_vlan_id}"
            )

        new_vlan_task = asyncio.sleep(0)
        if vlan_id and epg_name:
            new_vlan_task = self.helpers.get_or_create_vlan(vlan_id, epg_name, site, vrf)

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

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a segment in NetBox"""
        segment = await self.query_ops.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]

            # Get prefix
            prefix = await run_netbox_get(
                lambda: self.nb.ipam.prefixes.get(prefix_id),
                f"get prefix {prefix_id}"
            )

            # Apply updates
            if "$set" in update:
                updates = update["$set"]
                old_vlan_for_cleanup = await self._apply_prefix_updates(prefix, updates, segment)
                
                # Save changes FIRST before cleanup
                await run_netbox_write(
                    lambda: prefix.save(),
                    f"save prefix {prefix_id}"
                )

                # Clean up old VLAN if it was returned (AFTER save so NetBox sees the change)
                if old_vlan_for_cleanup:
                    await self.helpers.cleanup_unused_vlan(old_vlan_for_cleanup)

                # Invalidate cache since we modified data
                invalidate_cache(CACHE_KEY_PREFIXES)

            return True

        except Exception as e:
            logger.error(f"Error updating prefix in NetBox (query: {query}, update: {update}): {e}", exc_info=True)
            return False

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment from NetBox (prefix and associated VLAN, but not VLAN Group)"""
        segment = await self.query_ops.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]

            # Get the prefix object to check for associated VLAN
            prefix = await run_netbox_get(
                lambda: self.nb.ipam.prefixes.get(prefix_id),
                f"get prefix {prefix_id} for deletion"
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
                        lambda: self.nb.ipam.vlans.get(vlan_id),
                        f"get VLAN {vlan_id} for deletion"
                    )
                except Exception as e:
                    logger.warning(f"Error getting VLAN info for prefix {prefix_id}: {e}", exc_info=True)

            # Delete the prefix FIRST (this removes the dependency on the VLAN)
            await run_netbox_write(
                lambda: prefix.delete(),
                f"delete prefix {prefix_id}"
            )
            # NOW delete the VLAN (prefix is gone, so no dependency conflict)
            if vlan_obj:
                try:
                    await run_netbox_write(
                        lambda: vlan_obj.delete(),
                        f"delete VLAN {safe_get_attr(vlan_obj, 'vid', vlan_id)}"
                    )
                except Exception as e:
                    logger.warning(f"Error deleting VLAN {safe_get_attr(vlan_obj, 'vid', vlan_id)} after prefix deletion: {e}", exc_info=True)
                    # Don't fail the whole operation if VLAN deletion fails

            # Invalidate cache since we modified data
            invalidate_cache(CACHE_KEY_PREFIXES)
            invalidate_cache(CACHE_KEY_VLANS)

            return True

        except Exception as e:
            logger.error(f"Error deleting prefix from NetBox (query: {query}): {e}", exc_info=True)
            return False

    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        sort: Optional[List[tuple]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find and update a segment atomically"""
        segments = await self.query_ops.find(query)
        if not segments:
            return None

        # Apply sorting if specified
        if sort:
            for field, direction in reversed(sort):
                segments.sort(
                    key=lambda x: x.get(field, 0),
                    reverse=(direction == -1)
                )

        # Get first segment after sorting
        segment = segments[0]

        # Update it
        await self.update_one({"_id": segment["_id"]}, update)

        # Apply updates to in-memory segment instead of fetching from NetBox again
        updated_segment = segment.copy()
        if "$set" in update:
            updated_segment.update(update["$set"])
        return updated_segment
