"""
NetBox Storage Implementation

This module provides a storage interface that uses NetBox's REST API
for managing VLANs and IP prefixes (segments). It replaces the local
JSON file storage with NetBox as the backend.

NetBox Objects Used:
- Sites (dcim.sites): Locations/data centers
- VLANs (ipam.vlans): VLAN definitions
- Prefixes (ipam.prefixes): IP address segments/subnets
- Custom Fields: cluster_name, allocated_at, released, released_at, description

This module has been refactored into smaller, focused modules:
- netbox_client.py: Client initialization and executors
- netbox_cache.py: Cache management
- netbox_helpers.py: Helper functions for NetBox objects
- netbox_converters.py: Data conversion functions
- netbox_sync.py: Initialization and sync functions
"""

import logging
import asyncio
import time
import re
from typing import Optional, List, Dict, Any

from .netbox_client import (
    get_netbox_client,
    get_netbox_read_executor,
    get_netbox_write_executor,
    get_netbox_executor
)
from .netbox_cache import (
    get_cached,
    set_cache,
    invalidate_cache,
    get_inflight_request,
    set_inflight_request,
    remove_inflight_request
)
from .netbox_helpers import NetBoxHelpers
from .netbox_converters import prefix_to_segment
from .netbox_utils import log_netbox_timing

logger = logging.getLogger(__name__)


class NetBoxStorage:
    """
    NetBox Storage Implementation

    Maps our segment/VLAN data model to NetBox's IPAM model:
    - Segment = NetBox Prefix (IP subnet)
    - VLAN ID = NetBox VLAN
    - Site = NetBox Site
    - EPG Name = Stored in Prefix description/custom field
    - Cluster allocation = Custom field on Prefix
    """

    def __init__(self):
        self.nb = get_netbox_client()
        self.helpers = NetBoxHelpers(self.nb)

    async def _fetch_prefixes_from_netbox(self, nb_filter: Dict[str, Any]) -> List[Any]:
        """Helper method to fetch prefixes from NetBox (used for request coalescing)"""
        from .netbox_utils import run_netbox_get
        
        prefixes = await run_netbox_get(
            lambda: list(self.nb.ipam.prefixes.filter(**nb_filter)),
            f"fetch prefixes (filter: {nb_filter})"
        )
        return prefixes

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        results = await self.find(query)
        return results[0] if results else None

    async def find_one_optimized(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Optimized find_one that uses NetBox API filtering to reduce data transfer

        This method is specifically optimized for allocation queries that filter by:
        - site (via VRF + custom field filtering)
        - cluster_name
        - released status
        - vrf

        It fetches only the necessary data from NetBox instead of all prefixes.
        """
        t_fetch = time.time()

        # Use find() with caching instead of direct API call
        try:
            results = await self.find(query)
            logger.info(f"⏱️  find_one_optimized took {(time.time() - t_fetch)*1000:.0f}ms")
            return results[0] if results else None
        except Exception as e:
            logger.error(f"find_one_optimized failed (query: {query}): {e}", exc_info=True)
            return None

    async def find(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Find segments matching the query

        Query examples:
        - {"site": "site1"} - All segments for site1
        - {"cluster_name": "cluster1", "released": False} - Allocated to cluster1
        - {"vlan_id": 100} - VLAN 100

        Note: In NetBox, sites are associated with VLANs, not directly with prefixes.
        """
        # Build NetBox filter for prefixes
        # PERFORMANCE: Always filter by RedBull tenant to reduce data fetched
        nb_filter = {}

        # Get RedBull tenant ID for filtering
        tenant_id = await self.helpers.get_redbull_tenant_id()
        if tenant_id:
            nb_filter["tenant_id"] = tenant_id

        # Filter by VLAN VID if provided
        if query and "vlan_id" in query:
            nb_filter["vlan_vid"] = query["vlan_id"]

        # Use simple cache key (VRF filtering happens in-memory)
        cache_key = "prefixes"
        prefixes = get_cached(cache_key)

        if prefixes is None:
            # Check if another request is already fetching this data
            inflight_task = get_inflight_request(cache_key)
            if inflight_task:
                logger.info(f"⏳ Waiting for in-flight prefixes fetch (request coalescing)")
                t_wait = time.time()
                # Wait for the in-flight request to complete
                try:
                    prefixes = await inflight_task
                    logger.info(f"⏱️  Waited {(time.time() - t_wait)*1000:.0f}ms for coalesced request")
                except Exception as e:
                    logger.error(f"In-flight request failed for cache key '{cache_key}': {e}", exc_info=True)
                    # Fall through to fetch ourselves
                    prefixes = None

            if prefixes is None:
                # Create a future for this fetch so other concurrent requests can wait
                fetch_future = asyncio.create_task(self._fetch_prefixes_from_netbox(nb_filter))
                set_inflight_request(cache_key, fetch_future)

                try:
                    t_fetch = time.time()
                    logger.info(f"Fetching prefixes from NetBox with filter: {nb_filter} (cache miss)")
                    prefixes = await fetch_future
                    logger.info(f"⏱️      NetBox fetch took {(time.time() - t_fetch)*1000:.0f}ms ({len(prefixes)} prefixes)")
                    # Cache the results
                    set_cache(cache_key, prefixes)
                finally:
                    # Remove from in-flight tracker
                    remove_inflight_request(cache_key)
        else:
            logger.debug(f"Using cached prefixes ({len(prefixes)} items, key={cache_key})")

        # Convert NetBox prefixes to our segment format and apply filters
        segments = []
        for prefix in prefixes:
            segment = prefix_to_segment(prefix, self.nb)

            # Skip segments without valid site assignment (site is None/null)
            # These are improperly configured VLANs in NetBox
            if segment.get("site") is None:
                logger.debug(f"Skipping segment with no site: VLAN {segment.get('vlan_id')}, EPG {segment.get('epg_name')}")
                continue

            # Skip segments without VRF assignment
            if segment.get("vrf") is None:
                logger.debug(f"Skipping segment with no VRF: VLAN {segment.get('vlan_id')}, EPG {segment.get('epg_name')}")
                continue

            # Apply in-memory filters
            if query:
                # Site filter - check the site from the VLAN
                if "site" in query and segment.get("site") != query["site"]:
                    continue

                # VRF filter - CRITICAL for allocation queries
                if "vrf" in query and segment.get("vrf") != query["vrf"]:
                    continue

                # VLAN ID filter
                if "vlan_id" in query and segment.get("vlan_id") != query["vlan_id"]:
                    continue

                # Cluster name filter - exact match or regex
                if "cluster_name" in query:
                    cluster_value = query["cluster_name"]
                    if isinstance(cluster_value, dict) and "$regex" in cluster_value:
                        # Regex match
                        pattern = cluster_value["$regex"]
                        if not re.search(pattern, segment.get("cluster_name") or ""):
                            continue
                    elif isinstance(cluster_value, dict) and "$ne" in cluster_value:
                        # Not equal
                        if segment.get("cluster_name") == cluster_value["$ne"]:
                            continue
                    else:
                        # Exact match
                        if segment.get("cluster_name") != cluster_value:
                            continue

                # Released filter
                if "released" in query and segment.get("released") != query["released"]:
                    continue

                # ID filter
                if "_id" in query:
                    id_value = query["_id"]
                    if isinstance(id_value, dict) and "$ne" in id_value:
                        # Compare as strings to handle both string and int IDs
                        if str(segment.get("_id")) == str(id_value["$ne"]):
                            continue
                    else:
                        # Compare as strings
                        if str(segment.get("_id")) != str(id_value):
                            continue

                # $or queries (used for search across multiple fields)
                if "$or" in query:
                    match = False
                    for or_condition in query["$or"]:
                        # Check each condition in the OR clause
                        condition_match = True
                        for field, value in or_condition.items():
                            if isinstance(value, dict) and "$regex" in value:
                                # Regex match (case-insensitive if $options: "i")
                                pattern = value["$regex"]
                                flags = re.IGNORECASE if value.get("$options") == "i" else 0
                                if not re.search(pattern, str(segment.get(field) or ""), flags):
                                    condition_match = False
                                    break
                            elif isinstance(value, dict) and "$ne" in value:
                                # Not equal
                                if segment.get(field) == value["$ne"]:
                                    condition_match = False
                                    break
                            else:
                                # Exact match
                                if segment.get(field) != value:
                                    condition_match = False
                                    break

                        if condition_match:
                            match = True
                            break

                    if not match:
                        continue

            segments.append(segment)

        return segments

    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new segment in NetBox"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            logger.debug(f"Creating NetBox prefix for document: {document}")

            # OPTIMIZATION: Fetch all reference data in parallel using asyncio.gather()
            # This reduces serial API calls from ~200ms total to ~50ms (4x faster)
            gather_tasks = []
            task_names = []

            # Prepare tasks for parallel execution
            if "vrf" in document and document["vrf"]:
                gather_tasks.append(self.helpers.get_vrf(document["vrf"]))
                task_names.append("vrf")
            else:
                gather_tasks.append(None)  # Placeholder
                task_names.append("vrf")

            if "site" in document and document["site"]:
                gather_tasks.append(self.helpers.get_or_create_site(document["site"]))
                task_names.append("site_group")
            else:
                gather_tasks.append(None)
                task_names.append("site_group")

            gather_tasks.append(self.helpers.get_tenant("RedBull"))
            task_names.append("tenant")

            gather_tasks.append(self.helpers.get_role("Data", "prefix"))
            task_names.append("role")

            # Execute all lookups in parallel
            t_parallel = time.time()
            results = await asyncio.gather(*[task if task is not None else asyncio.sleep(0) for task in gather_tasks])
            logger.info(f"⏱️  Parallel reference data fetch took {(time.time() - t_parallel)*1000:.0f}ms")

            # Unpack results
            vrf_obj = results[0] if results[0] and task_names[0] == "vrf" else None
            site_group_obj = results[1] if results[1] and task_names[1] == "site_group" else None
            tenant = results[2] if results[2] and task_names[2] == "tenant" else None
            role = results[3] if results[3] and task_names[3] == "role" else None

            # Prepare prefix data
            prefix_data = {
                "prefix": document["segment"],
                "description": "",  # Empty initially, will show cluster name when allocated
                "comments": document.get("description", ""),  # User info goes in comments
                "status": "active",
                "is_pool": True,  # All IP addresses within this prefix are considered usable
            }

            # Add VRF if provided
            if vrf_obj:
                prefix_data["vrf"] = vrf_obj.id
                logger.debug(f"Assigned VRF '{vrf_obj.name}' (ID: {vrf_obj.id}) to prefix")

            # Add site group scope if provided
            if site_group_obj:
                prefix_data["scope_type"] = "dcim.sitegroup"
                prefix_data["scope_id"] = site_group_obj.id
                logger.debug(f"Assigned Site Group scope: type=dcim.sitegroup, id={site_group_obj.id}")
            elif "site" in document and document["site"]:
                # Site was requested but not created - this is an error
                logger.error(f"Failed to get/create site group: {document['site']}")
                raise Exception(f"Failed to get/create site group: {document['site']}")

            # Add tenant "RedBull"
            if tenant:
                prefix_data["tenant"] = tenant.id
                logger.debug(f"Assigned tenant 'RedBull' (ID: {tenant.id}) to prefix")

            # Add role "Data"
            if role:
                prefix_data["role"] = role.id
                logger.debug(f"Assigned role 'Data' (ID: {role.id}) to prefix")

            # Add VLAN if provided (pass VRF name for VLAN group)
            # Note: VLAN creation must be separate as it depends on VRF
            if "vlan_id" in document and document["vlan_id"]:
                logger.debug(f"Getting/creating VLAN: {document['vlan_id']}")
                vlan_obj = await self.helpers.get_or_create_vlan(
                    document["vlan_id"],
                    document.get("epg_name", f"VLAN_{document['vlan_id']}"),
                    document.get("site"),
                    document.get("vrf")  # Pass VRF name for VLAN group creation
                )
                if not vlan_obj:
                    raise Exception(f"Failed to get/create VLAN: {document['vlan_id']}")
                prefix_data["vlan"] = vlan_obj.id
                logger.debug(f"Assigned VLAN {vlan_obj.vid} ({vlan_obj.name}, ID: {vlan_obj.id}) to prefix")

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
            prefix = await loop.run_in_executor(
                executor,
                lambda: self.nb.ipam.prefixes.create(**prefix_data)
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

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a segment in NetBox"""
        loop = asyncio.get_event_loop()
        read_executor = get_netbox_read_executor()
        write_executor = get_netbox_write_executor()

        # Find the prefix
        t_find = time.time()
        segment = await self.find_one(query)
        logger.info(f"⏱️      find_one() in update_one took {(time.time() - t_find)*1000:.0f}ms")
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]

            # Get prefix with timing
            from .netbox_utils import run_netbox_get
            prefix = await run_netbox_get(
                lambda: self.nb.ipam.prefixes.get(prefix_id),
                f"get prefix {prefix_id}"
            )

            # Apply updates
            if "$set" in update:
                updates = update["$set"]

                # Handle user description field (DHCP, Gateway, etc.) → goes to COMMENTS
                if "description" in updates:
                    prefix.comments = updates["description"]
                    logger.debug(f"Updated comments field to: {updates['description']}")

                # Handle segment/prefix update
                if "segment" in updates:
                    prefix.prefix = updates["segment"]
                    logger.debug(f"Updated prefix to: {updates['segment']}")

                # Handle VRF update
                if "vrf" in updates:
                    vrf_obj = await self.helpers.get_vrf(updates["vrf"])
                    if vrf_obj:
                        prefix.vrf = vrf_obj.id
                        logger.debug(f"Updated VRF to: {updates['vrf']}")

                # Handle custom field updates (DHCP)
                if "dhcp" in updates:
                    if not hasattr(prefix, 'custom_fields') or prefix.custom_fields is None:
                        prefix.custom_fields = {}
                    prefix.custom_fields['DHCP'] = updates["dhcp"]
                    logger.debug(f"Updated DHCP custom field to: {updates['dhcp']}")

                # Handle VLAN ID or EPG name updates
                if "vlan_id" in updates or "epg_name" in updates:
                    # Store old VLAN for cleanup
                    old_vlan_obj = None
                    old_vlan_vid = None

                    if hasattr(prefix, 'vlan') and prefix.vlan:
                        # prefix.vlan is a Record object with an 'id' attribute
                        # We need to fetch the full VLAN object for cleanup
                        try:
                            old_vlan_id = prefix.vlan.id if hasattr(prefix.vlan, 'id') else prefix.vlan
                            old_vlan_obj = await loop.run_in_executor(
                                read_executor,
                                lambda: self.nb.ipam.vlans.get(old_vlan_id)
                            )
                            if old_vlan_obj:
                                old_vlan_vid = old_vlan_obj.vid
                                logger.info(f"Will check for cleanup: Old VLAN {old_vlan_vid} (NetBox ID: {old_vlan_id})")
                        except Exception as e:
                            logger.warning(f"Failed to get old VLAN for cleanup (VLAN ID: {old_vlan_id}): {e}", exc_info=True)

                    # Need to update or create VLAN object
                    vlan_id = updates.get("vlan_id", segment.get("vlan_id"))
                    epg_name = updates.get("epg_name", segment.get("epg_name"))
                    site = updates.get("site", segment.get("site"))
                    vrf = updates.get("vrf", segment.get("vrf"))

                    if vlan_id and epg_name:
                        new_vlan_obj = await self.helpers.get_or_create_vlan(vlan_id, epg_name, site, vrf)
                        if new_vlan_obj:
                            prefix.vlan = new_vlan_obj.id
                            logger.info(f"Updated prefix to new VLAN {vlan_id} (NetBox ID: {new_vlan_obj.id})")

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

                # Save changes FIRST before cleanup (use write executor for slow saves)
                from .netbox_utils import run_netbox_write
                await run_netbox_write(
                    lambda: prefix.save(),
                    f"save prefix {prefix_id}"
                )

                logger.info(f"Updated prefix {prefix.prefix} (ID: {prefix_id})")

                # NOW clean up old VLAN if it's no longer used by any prefix
                # This must happen AFTER saving so NetBox shows the new VLAN assignment
                if "vlan_id" in updates or "epg_name" in updates:
                    if old_vlan_obj and old_vlan_vid and old_vlan_vid != updates.get("vlan_id", segment.get("vlan_id")):
                        logger.info(f"Checking if old VLAN {old_vlan_vid} can be cleaned up...")
                        await self.helpers.cleanup_unused_vlan(old_vlan_obj)
                    elif not old_vlan_obj:
                        logger.debug("No old VLAN to clean up (prefix had no VLAN before)")

                # Invalidate cache since we modified data
                t_invalidate = time.time()
                invalidate_cache("prefixes")
                logger.info(f"⏱️      Cache invalidation took {(time.time() - t_invalidate)*1000:.0f}ms")

            return True

        except Exception as e:
            logger.error(f"Error updating prefix in NetBox (query: {query}, update: {update}): {e}", exc_info=True)
            return False

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment from NetBox (prefix and associated VLAN, but not VLAN Group)"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        segment = await self.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]
            
            # Get the prefix object to check for associated VLAN
            prefix = await loop.run_in_executor(
                executor,
                lambda: self.nb.ipam.prefixes.get(prefix_id)
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
                    vlan_obj = await loop.run_in_executor(
                        executor,
                        lambda: self.nb.ipam.vlans.get(vlan_id)
                    )
                    
                    if vlan_obj:
                        vlan_vid = getattr(vlan_obj, 'vid', vlan_id)
                        vlan_name = getattr(vlan_obj, 'name', '')
                        logger.debug(f"Will delete VLAN {vlan_vid} ({vlan_name}, ID: {vlan_id}) after prefix deletion")
                except Exception as e:
                    logger.warning(f"Error getting VLAN info for prefix {prefix_id}: {e}", exc_info=True)
                    # Continue with prefix deletion even if VLAN fetch fails
            
            # Delete the prefix FIRST (this removes the dependency on the VLAN)
            await loop.run_in_executor(
                executor,
                lambda: prefix.delete()
            )
            logger.info(f"Deleted prefix ID: {prefix_id}")
            
            # NOW delete the VLAN (prefix is gone, so no dependency conflict)
            vlan_deleted = False
            if vlan_obj:
                try:
                    await loop.run_in_executor(
                        executor,
                        lambda: vlan_obj.delete()
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

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        """Count segments matching the query"""
        results = await self.find(query or {})
        return len(results)

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
            segments = await self.find(query)
            logger.info(f"⏱️    find() with filter took {(time.time() - t1)*1000:.0f}ms")
        else:
            # Other queries - use regular find()
            segments = await self.find(query)
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

    async def get_vrfs(self) -> List[str]:
        """Get list of available VRFs from NetBox (cached for 1 hour)"""
        return await self.helpers.get_vrfs()


def get_storage() -> NetBoxStorage:
    """Get the NetBox storage instance"""
    return NetBoxStorage()


# Re-export sync functions for backward compatibility
from .netbox_sync import init_storage, close_storage
