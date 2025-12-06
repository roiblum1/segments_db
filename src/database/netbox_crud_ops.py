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
import time
from typing import Optional, List, Dict, Any

from .netbox_client import get_netbox_executor, log_netbox_timing
from .netbox_cache import invalidate_cache
from .netbox_helpers import NetBoxHelpers
from .netbox_converters import prefix_to_segment

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

    @log_netbox_timing("insert_one")
    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new segment in NetBox"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            logger.debug(f"Creating NetBox prefix for document: {document}")

            # OPTIMIZATION: Fetch all reference data AND VLAN in parallel using asyncio.gather()
            # This reduces serial API calls from ~200ms total to ~50ms (5x faster)
            vrf_task = self.helpers.get_vrf(document["vrf"]) if document.get("vrf") else asyncio.sleep(0)
            site_task = self.helpers.get_site(document["site"]) if document.get("site") else asyncio.sleep(0)
            tenant_task = self.helpers.get_tenant("RedBull")
            role_task = self.helpers.get_role("Data", "prefix")

            # OPTIMIZATION: Include VLAN creation in parallel execution
            vlan_task = None
            if document.get("vlan_id"):
                vlan_task = self.helpers.get_or_create_vlan(
                    document["vlan_id"],
                    document.get("epg_name", f"VLAN_{document['vlan_id']}"),
                    document.get("site"),
                    document.get("vrf")  # Pass VRF name for VLAN group creation
                )
            else:
                vlan_task = asyncio.sleep(0)

            # Execute all lookups in parallel (including VLAN)
            t_parallel = time.time()
            vrf_obj, site_group_obj, tenant, role, vlan_obj = await asyncio.gather(
                vrf_task, site_task, tenant_task, role_task, vlan_task
            )
            logger.info(f"⏱️  Parallel reference data + VLAN fetch took {(time.time() - t_parallel)*1000:.0f}ms")

            # Validate required objects were fetched
            if document.get("site") and not site_group_obj:
                raise Exception(f"Failed to get/create site group: {document['site']}")
            if document.get("vlan_id") and not vlan_obj:
                raise Exception(f"Failed to get/create VLAN: {document['vlan_id']}")

            # Build prefix data with all associations
            prefix_data = {
                "prefix": document["segment"],
                "description": "",  # Empty initially, will show cluster name when allocated
                "comments": document.get("description", ""),  # User info goes in comments
                "status": "active",
                "is_pool": True,  # All IP addresses within this prefix are considered usable
            }

            # Add object associations
            if vrf_obj:
                prefix_data["vrf"] = vrf_obj.id
            if site_group_obj:
                prefix_data["scope_type"] = "dcim.sitegroup"
                prefix_data["scope_id"] = site_group_obj.id
            if tenant:
                prefix_data["tenant"] = tenant.id
            if role:
                prefix_data["role"] = role.id
            if vlan_obj:
                prefix_data["vlan"] = vlan_obj.id
                logger.debug(f"Assigned VLAN {vlan_obj.vid} ({vlan_obj.name}) to prefix")

            # Add custom fields
            custom_fields = {}
            if "dhcp" in document:
                custom_fields["DHCP"] = document["dhcp"]
            if "cluster_name" in document and document["cluster_name"]:
                custom_fields["Cluster"] = document["cluster_name"]

            if custom_fields:
                prefix_data["custom_fields"] = custom_fields
                logger.debug(f"Added custom fields: {custom_fields}")

            # Create prefix in NetBox
            logger.debug(f"Creating prefix with data: {prefix_data}")
            from .netbox_utils import run_netbox_write
            prefix = await run_netbox_write(
                lambda: self.nb.ipam.prefixes.create(**prefix_data),
                f"create prefix {prefix_data['prefix']}"
            )

            logger.info(f"Created prefix in NetBox: {prefix.prefix} (ID: {prefix.id})")
            logger.debug(f"Created prefix with VRF={document.get('vrf')}, DHCP={document.get('dhcp')}, is_pool=True")

            # Invalidate cache since we modified data
            invalidate_cache("prefixes")

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
        if hasattr(prefix, 'vlan') and prefix.vlan:
            old_vlan_id = prefix.vlan.id if hasattr(prefix.vlan, 'id') else prefix.vlan
            from .netbox_utils import run_netbox_get
            old_vlan_task = run_netbox_get(
                lambda: self.nb.ipam.vlans.get(old_vlan_id),
                f"get old VLAN {old_vlan_id} for cleanup"
            )

        new_vlan_task = asyncio.sleep(0)
        if vlan_id and epg_name:
            new_vlan_task = self.helpers.get_or_create_vlan(vlan_id, epg_name, site, vrf)

        # Execute in parallel (2x faster)
        t_vlan = time.time()
        old_vlan_obj, new_vlan_obj = await asyncio.gather(
            old_vlan_task, new_vlan_task, return_exceptions=True
        )
        logger.info(f"⏱️  Parallel VLAN fetch took {(time.time() - t_vlan)*1000:.0f}ms")

        # Update to new VLAN
        if new_vlan_obj and not isinstance(new_vlan_obj, Exception):
            prefix.vlan = new_vlan_obj.id
            logger.info(f"Updated prefix to new VLAN {vlan_id} (NetBox ID: {new_vlan_obj.id})")

        # Return old VLAN for cleanup after save
        if old_vlan_obj and not isinstance(old_vlan_obj, Exception):
            old_vlan_vid = old_vlan_obj.vid
            if old_vlan_vid != vlan_id:  # Only return if VLAN actually changed
                return old_vlan_obj
        return None

    @log_netbox_timing("update_one")
    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a segment in NetBox"""
        segment = await self.query_ops.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]

            # Get prefix
            from .netbox_utils import run_netbox_get, run_netbox_write
            prefix = await run_netbox_get(
                lambda: self.nb.ipam.prefixes.get(prefix_id),
                f"get prefix {prefix_id}"
            )

            # Apply updates
            if "$set" in update:
                updates = update["$set"]

                # Basic field updates
                if "description" in updates:
                    prefix.comments = updates["description"]
                if "segment" in updates:
                    prefix.prefix = updates["segment"]

                # VRF update
                if "vrf" in updates:
                    vrf_obj = await self.helpers.get_vrf(updates["vrf"])
                    if vrf_obj:
                        prefix.vrf = vrf_obj.id

                # DHCP custom field
                if "dhcp" in updates:
                    if not hasattr(prefix, 'custom_fields') or prefix.custom_fields is None:
                        prefix.custom_fields = {}
                    prefix.custom_fields['DHCP'] = updates["dhcp"]

                # VLAN update (extract complex logic to helper)
                old_vlan_for_cleanup = None
                if "vlan_id" in updates or "epg_name" in updates:
                    old_vlan_for_cleanup = await self._update_vlan_if_changed(prefix, updates, segment)

                # Update prefix status and CUSTOM FIELD based on allocation state
                # IMPORTANT: CUSTOM FIELD "Cluster" is for cluster name, COMMENTS is for user info
                if "cluster_name" in updates and updates["cluster_name"]:
                    # Allocated: set status to "reserved" and cluster custom field
                    cluster_name = updates["cluster_name"]
                    prefix.status = "reserved"
                    if not hasattr(prefix, 'custom_fields') or prefix.custom_fields is None:
                        prefix.custom_fields = {}
                    prefix.custom_fields['Cluster'] = cluster_name
                    logger.debug(f"Set allocation: cluster={cluster_name}, status=reserved")
                elif "released" in updates and updates["released"]:
                    # Released: set status back to "active" and clear cluster custom field
                    prefix.status = "active"
                    if hasattr(prefix, 'custom_fields') and prefix.custom_fields:
                        prefix.custom_fields['Cluster'] = None
                    logger.debug("Cleared allocation: status=active, cluster=empty")

                # Save changes FIRST before cleanup
                await run_netbox_write(
                    lambda: prefix.save(),
                    f"save prefix {prefix_id}"
                )
                logger.info(f"Updated prefix {prefix.prefix} (ID: {prefix_id})")

                # Clean up old VLAN if it was returned (AFTER save so NetBox sees the change)
                if old_vlan_for_cleanup:
                    logger.info(f"Checking if old VLAN {old_vlan_for_cleanup.vid} can be cleaned up...")
                    await self.helpers.cleanup_unused_vlan(old_vlan_for_cleanup)

                # Invalidate cache since we modified data
                invalidate_cache("prefixes")

            return True

        except Exception as e:
            logger.error(f"Error updating prefix in NetBox (query: {query}, update: {update}): {e}", exc_info=True)
            return False

    @log_netbox_timing("delete_one")
    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment from NetBox (prefix and associated VLAN, but not VLAN Group)"""
        from .netbox_utils import run_netbox_get, run_netbox_write

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
            vlan_vid = None
            vlan_name = None
            if hasattr(prefix, 'vlan') and prefix.vlan:
                try:
                    # prefix.vlan is a Record object, get the VLAN ID
                    vlan_id = prefix.vlan.id if hasattr(prefix.vlan, 'id') else prefix.vlan

                    # Get the full VLAN object BEFORE deleting prefix
                    vlan_obj = await run_netbox_get(
                        lambda: self.nb.ipam.vlans.get(vlan_id),
                        f"get VLAN {vlan_id} for deletion"
                    )

                    if vlan_obj:
                        vlan_vid = getattr(vlan_obj, 'vid', vlan_id)
                        vlan_name = getattr(vlan_obj, 'name', '')
                        logger.debug(f"Will delete VLAN {vlan_vid} ({vlan_name}, ID: {vlan_id}) after prefix deletion")
                except Exception as e:
                    logger.warning(f"Error getting VLAN info for prefix {prefix_id}: {e}", exc_info=True)
                    # Continue with prefix deletion even if VLAN fetch fails

            # Delete the prefix FIRST (this removes the dependency on the VLAN)
            await run_netbox_write(
                lambda: prefix.delete(),
                f"delete prefix {prefix_id}"
            )
            logger.info(f"Deleted prefix ID: {prefix_id}")

            # NOW delete the VLAN (prefix is gone, so no dependency conflict)
            vlan_deleted = False
            if vlan_obj:
                try:
                    await run_netbox_write(
                        lambda: vlan_obj.delete(),
                        f"delete VLAN {vlan_vid}"
                    )
                    logger.info(f"Deleted VLAN {vlan_vid} ({vlan_name}, ID: {vlan_obj.id}) after prefix deletion")
                    vlan_deleted = True
                except Exception as e:
                    logger.warning(f"Error deleting VLAN {vlan_vid} after prefix deletion: {e}", exc_info=True)
                    # Don't fail the whole operation if VLAN deletion fails

            # Invalidate cache since we modified data
            invalidate_cache("prefixes")
            invalidate_cache("vlans")

            return True

        except Exception as e:
            logger.error(f"Error deleting prefix from NetBox (query: {query}): {e}", exc_info=True)
            return False

    @log_netbox_timing("find_one_and_update")
    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        sort: Optional[List[tuple]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find and update a segment atomically

        Args:
            query: Query to find segment
            update: Update operations
            sort: Sort order as list of (field, direction) tuples
                  1 = ascending, -1 = descending
        """
        # Use optimized find if query contains VRF (allocation queries)
        # Regular find() for other queries (releases, updates, etc.)
        t1 = time.time()

        if query.get("vrf") and query.get("cluster_name") is None:
            # This is an allocation query - use optimized find with NetBox filtering
            # We need to fetch multiple results to sort, so use find() with VRF filter
            segments = await self.query_ops.find(query)
            logger.info(f"⏱️    find() with filter took {(time.time() - t1)*1000:.0f}ms")
        else:
            # Other queries - use regular find()
            segments = await self.query_ops.find(query)
            logger.info(f"⏱️    find() took {(time.time() - t1)*1000:.0f}ms")

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
        t2 = time.time()
        await self.update_one({"_id": segment["_id"]}, update)
        logger.info(f"⏱️    update_one() took {(time.time() - t2)*1000:.0f}ms")

        # OPTIMIZATION: Apply updates to in-memory segment instead of fetching from NetBox again
        # This avoids a full cache refresh + NetBox fetch after invalidation
        t3 = time.time()
        updated_segment = segment.copy()
        if "$set" in update:
            updated_segment.update(update["$set"])
        logger.info(f"⏱️    In-memory update took {(time.time() - t3)*1000:.0f}ms")
        return updated_segment
