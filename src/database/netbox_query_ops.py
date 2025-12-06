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
import re
from typing import Optional, List, Dict, Any

from .netbox_client import get_netbox_client, run_netbox_get
from .netbox_cache import (
    get_cached,
    set_cache,
    get_inflight_request,
    set_inflight_request,
    remove_inflight_request
)
from .netbox_helpers import NetBoxHelpers
from .netbox_utils import prefix_to_segment
from .netbox_constants import CACHE_KEY_PREFIXES

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
        prefixes = await run_netbox_get(
            lambda: list(self.nb.ipam.prefixes.filter(**nb_filter)),
            f"fetch prefixes"
        )
        return prefixes

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        results = await self.find(query)
        return results[0] if results else None

    async def find_one_optimized(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Optimized find_one that uses NetBox API filtering to reduce data transfer"""
        results = await self.find(query)
        return results[0] if results else None

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
        cache_key = CACHE_KEY_PREFIXES
        prefixes = get_cached(cache_key)

        if prefixes is None:
            # Check if another request is already fetching this data
            inflight_task = get_inflight_request(cache_key)
            if inflight_task:
                try:
                    prefixes = await inflight_task
                except Exception as e:
                    logger.error(f"In-flight request failed: {e}")
                    prefixes = None

            if prefixes is None:
                fetch_future = asyncio.create_task(self._fetch_prefixes_from_netbox(nb_filter))
                set_inflight_request(cache_key, fetch_future)
                try:
                    prefixes = await fetch_future
                    set_cache(cache_key, prefixes)
                finally:
                    remove_inflight_request(cache_key)

        # Convert NetBox prefixes to our segment format and apply filters
        segments = []
        for prefix in prefixes:
            segment = prefix_to_segment(prefix, self.nb)

            # Skip invalid segments
            if not segment.get("site") or not segment.get("vrf"):
                continue

            # Apply filters
            if query and not self._matches_query(segment, query):
                continue

            segments.append(segment)

        return segments

    def _matches_query(self, segment: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if segment matches query filters"""
        # Handle $or queries first
        if "$or" in query:
            for or_condition in query["$or"]:
                if self._matches_condition(segment, or_condition):
                    break
            else:
                return False

        # Handle individual field filters
        for field, value in query.items():
            if field == "$or":
                continue

            segment_value = segment.get(field)

            # Handle dict operators ($regex, $ne)
            if isinstance(value, dict):
                if "$regex" in value:
                    pattern = value["$regex"]
                    flags = re.IGNORECASE if value.get("$options") == "i" else 0
                    if not re.search(pattern, str(segment_value or ""), flags):
                        return False
                elif "$ne" in value:
                    if segment_value == value["$ne"]:
                        return False
            # Handle None/null matching (both Python None and JSON null)
            elif value is None:
                if segment_value is not None and segment_value != "null":
                    return False
            # Case-insensitive match for site field
            elif field == "site" and isinstance(value, str) and isinstance(segment_value, str):
                if value.lower() != segment_value.lower():
                    return False
            # Exact match for other fields
            elif segment_value != value:
                return False

        return True

    def _matches_condition(self, segment: Dict[str, Any], condition: Dict[str, Any]) -> bool:
        """Check if segment matches a single condition (used for $or)"""
        for field, value in condition.items():
            segment_value = segment.get(field)
            if isinstance(value, dict):
                if "$regex" in value:
                    pattern = value["$regex"]
                    flags = re.IGNORECASE if value.get("$options") == "i" else 0
                    if not re.search(pattern, str(segment_value or ""), flags):
                        return False
                elif "$ne" in value:
                    if segment_value == value["$ne"]:
                        return False
            # Handle None/null matching
            elif value is None:
                if segment_value is not None and segment_value != "null":
                    return False
            # Case-insensitive match for site field
            elif field == "site" and isinstance(value, str) and isinstance(segment_value, str):
                if value.lower() != segment_value.lower():
                    return False
            elif segment_value != value:
                return False
        return True

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        """Count segments matching the query"""
        results = await self.find(query or {})
        return len(results)
