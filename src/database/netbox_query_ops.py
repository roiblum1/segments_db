"""
NetBox Query Operations

This module handles all read operations for NetBox storage:
- Finding segments with caching and request coalescing
- Optimized queries for allocation
- Counting documents

Separated from CRUD operations for better maintainability.
"""

import logging
import asyncio
import time
import re
from typing import Optional, List, Dict, Any

from .netbox_client import get_netbox_client, log_netbox_timing
from .netbox_cache import (
    get_cached,
    set_cache,
    get_inflight_request,
    set_inflight_request,
    remove_inflight_request
)
from .netbox_helpers import NetBoxHelpers
from .netbox_converters import prefix_to_segment

logger = logging.getLogger(__name__)


class NetBoxQueryOps:
    """
    NetBox Query Operations

    Handles all read operations with caching and optimization:
    - find(): Main query method with caching
    - find_one(): Single result wrapper
    - find_one_optimized(): Optimized for allocation queries
    - count_documents(): Count matching segments
    """

    def __init__(self, nb_client, helpers: NetBoxHelpers):
        self.nb = nb_client
        self.helpers = helpers

    async def _fetch_prefixes_from_netbox(self, nb_filter: Dict[str, Any]) -> List[Any]:
        """Helper method to fetch prefixes from NetBox (used for request coalescing)"""
        from .netbox_utils import run_netbox_get

        prefixes = await run_netbox_get(
            lambda: list(self.nb.ipam.prefixes.filter(**nb_filter)),
            f"fetch prefixes (filter: {nb_filter})"
        )
        return prefixes

    @log_netbox_timing("find_one")
    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        results = await self.find(query)
        return results[0] if results else None

    @log_netbox_timing("find_one_optimized")
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

    @log_netbox_timing("find")
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

    @log_netbox_timing("count_documents")
    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        """Count segments matching the query"""
        results = await self.find(query or {})
        return len(results)
