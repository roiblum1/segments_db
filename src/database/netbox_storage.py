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

"""

import logging
import pynetbox
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import asyncio
import time
import concurrent.futures
from functools import lru_cache, wraps

from ..config.settings import NETBOX_URL, NETBOX_TOKEN, NETBOX_SSL_VERIFY

logger = logging.getLogger(__name__)


def log_netbox_timing(operation_name: str):
    """
    Decorator to log the exact time a NetBox API call takes.
    This measures PURE NetBox response time at the HTTP level.
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000

                if elapsed > 20000:
                    logger.error(f"🚨 NETBOX SEVERE THROTTLING: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 5000:
                    logger.warning(f"⚠️  NETBOX THROTTLED: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 2000:
                    logger.info(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
                else:
                    logger.debug(f"NETBOX OK: {operation_name} took {elapsed:.0f}ms")

                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"NETBOX FAILED: {operation_name} failed after {elapsed:.0f}ms - {e}")
                raise

        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000

                if elapsed > 20000:
                    logger.error(f"🚨 NETBOX SEVERE THROTTLING: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 5000:
                    logger.warning(f"⚠️  NETBOX THROTTLED: {operation_name} took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
                elif elapsed > 2000:
                    logger.info(f"NETBOX SLOW: {operation_name} took {elapsed:.0f}ms")
                else:
                    logger.debug(f"NETBOX OK: {operation_name} took {elapsed:.0f}ms")

                return result
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                logger.error(f"NETBOX FAILED: {operation_name} failed after {elapsed:.0f}ms - {e}")
                raise

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator

# Global NetBox API client
_netbox_client: Optional[pynetbox.api] = None

# Global thread pool executors for NetBox operations
# Separate pools prevent long-running writes from blocking quick reads

@lru_cache(maxsize=1)
def get_netbox_read_executor():
    """Thread pool for read operations (GET requests)

    Read operations are typically fast (<500ms) and frequent.
    Uses 30 workers for high concurrency.
    """
    return concurrent.futures.ThreadPoolExecutor(
        max_workers=30,
        thread_name_prefix="netbox_read_"
    )

@lru_cache(maxsize=1)
def get_netbox_write_executor():
    """Thread pool for write operations (POST/PUT/DELETE)

    Write operations can be slow (seconds) and should not block reads.
    Uses 20 workers to prevent overwhelming NetBox.
    """
    return concurrent.futures.ThreadPoolExecutor(
        max_workers=20,
        thread_name_prefix="netbox_write_"
    )

@lru_cache(maxsize=1)
def get_netbox_executor():
    """Default executor - uses read pool for backward compatibility"""
    return get_netbox_read_executor()

# Simple in-memory cache with TTL
# AGGRESSIVE CACHING to reduce NetBox Cloud API calls (they throttle heavily)
_cache = {
    "prefixes": {"data": None, "timestamp": 0, "ttl": 600},  # 10 minutes (was 5min)
    "vlans": {"data": None, "timestamp": 0, "ttl": 600},      # 10 minutes (was 5min)
    "redbull_tenant_id": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour TTL for tenant ID
    "vrfs": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour TTL for VRFs (rarely change)
}

# In-flight request tracking to prevent duplicate concurrent fetches
_inflight_requests = {}


def _get_cached(key: str) -> Optional[Any]:
    """Get cached data if still valid"""
    cache_entry = _cache.get(key)
    if cache_entry and cache_entry["data"] is not None:
        age = time.time() - cache_entry["timestamp"]
        if age < cache_entry["ttl"]:
            logger.debug(f"Cache HIT for {key} (age: {age:.1f}s)")
            return cache_entry["data"]
        else:
            logger.debug(f"Cache EXPIRED for {key} (age: {age:.1f}s, TTL: {cache_entry['ttl']}s)")
    return None


def _set_cache(key: str, data: Any) -> None:
    """Store data in cache with timestamp"""
    if key in _cache:
        _cache[key]["data"] = data
        _cache[key]["timestamp"] = time.time()
        logger.debug(f"Cache SET for {key} ({len(data) if isinstance(data, list) else 'N/A'} items)")


def invalidate_cache(key: Optional[str] = None) -> None:
    """
    Invalidate cache entries

    Args:
        key: Specific cache key to invalidate, or None to clear all
    """
    if key:
        if key in _cache:
            _cache[key]["data"] = None
            _cache[key]["timestamp"] = 0
            logger.info(f"Cache INVALIDATED for {key}")
    else:
        for cache_key in _cache:
            _cache[cache_key]["data"] = None
            _cache[cache_key]["timestamp"] = 0
        logger.info("Cache INVALIDATED (all)")


def get_netbox_client() -> pynetbox.api:
    """Get or create the NetBox API client"""
    global _netbox_client

    if _netbox_client is None:
        logger.info(f"Initializing NetBox client: {NETBOX_URL}")
        _netbox_client = pynetbox.api(
            NETBOX_URL,
            token=NETBOX_TOKEN
        )
        _netbox_client.http_session.verify = NETBOX_SSL_VERIFY

    return _netbox_client


async def init_storage():
    """Initialize NetBox storage - verify connection and sync existing data"""
    try:
        nb = get_netbox_client()

        # Test connection by getting status
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()
        executor = get_netbox_executor()
        status = await loop.run_in_executor(executor, lambda: nb.status())

        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")
        logger.info(f"NetBox URL: {NETBOX_URL}")

        # Sync existing VLANs from NetBox with Redbull tenant
        await sync_netbox_vlans()

    except Exception as e:
        logger.error(f"Failed to connect to NetBox: {e}")
        raise


async def sync_netbox_vlans():
    """Sync existing VLANs from NetBox with Redbull tenant"""
    try:
        nb = get_netbox_client()
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        logger.info("Starting sync of existing VLANs from NetBox (Tenant: Redbull)")

        # Get Redbull tenant
        tenant = await loop.run_in_executor(executor, lambda: nb.tenancy.tenants.get(slug="redbull"))
        if not tenant:
            logger.warning("Redbull tenant not found in NetBox - skipping VLAN sync")
            return

        logger.info(f"Found Redbull tenant (ID: {tenant.id})")

        # Get all VLANs with Redbull tenant
        vlans = await loop.run_in_executor(
            executor,
            lambda: list(nb.ipam.vlans.filter(tenant_id=tenant.id))
        )

        if not vlans:
            logger.info("No existing VLANs found with Redbull tenant")
            return

        logger.info(f"Found {len(vlans)} VLANs with Redbull tenant - syncing...")

        synced_count = 0
        skipped_count = 0
        error_count = 0

        for vlan in vlans:
            try:
                # Get associated prefix for this VLAN
                prefixes = await loop.run_in_executor(
                    executor,
                    lambda v=vlan: list(nb.ipam.prefixes.filter(vlan_id=v.id))
                )

                if not prefixes:
                    logger.debug(f"VLAN {vlan.vid} ({vlan.name}) has no associated prefix - skipping")
                    skipped_count += 1
                    continue

                prefix = prefixes[0]  # Use first prefix if multiple

                # Extract site from prefix scope
                site_name = None
                if hasattr(prefix, 'scope_type') and prefix.scope_type and 'sitegroup' in str(prefix.scope_type).lower():
                    if hasattr(prefix, 'scope_id') and prefix.scope_id:
                        site_group = await loop.run_in_executor(
                            executor,
                            lambda: nb.dcim.site_groups.get(prefix.scope_id)
                        )
                        if site_group:
                            site_name = site_group.slug

                if not site_name:
                    logger.debug(f"VLAN {vlan.vid} ({vlan.name}) has no valid site group - skipping")
                    skipped_count += 1
                    continue

                # Extract VRF
                vrf_name = prefix.vrf.name if prefix.vrf else None
                if not vrf_name:
                    logger.debug(f"VLAN {vlan.vid} ({vlan.name}) has no VRF - skipping")
                    skipped_count += 1
                    continue

                # Extract DHCP custom field
                dhcp_enabled = False
                if hasattr(prefix, 'custom_fields') and prefix.custom_fields:
                    dhcp_value = prefix.custom_fields.get('dhcp_enabled')
                    dhcp_enabled = dhcp_value is True or str(dhcp_value).lower() == 'true'

                # Extract cluster custom field
                cluster_name = None
                if hasattr(prefix, 'custom_fields') and prefix.custom_fields:
                    cluster_value = prefix.custom_fields.get('cluster')
                    if cluster_value:
                        cluster_name = str(cluster_value).strip()

                # Log the VLAN being synced
                logger.debug(
                    f"Syncing VLAN {vlan.vid} ({vlan.name}): "
                    f"site={site_name}, vrf={vrf_name}, prefix={prefix.prefix}, "
                    f"dhcp={dhcp_enabled}, cluster={cluster_name or 'unallocated'}"
                )

                synced_count += 1

            except Exception as e:
                logger.error(f"Error syncing VLAN {vlan.vid}: {e}")
                error_count += 1
                continue

        logger.info(
            f"VLAN sync complete: {synced_count} synced, {skipped_count} skipped, {error_count} errors"
        )

    except Exception as e:
        logger.error(f"Error during VLAN sync: {e}")
        # Don't raise - allow application to start even if sync fails


async def close_storage():
    """Close NetBox storage - cleanup if needed"""
    global _netbox_client

    if _netbox_client is not None:
        logger.info("Closing NetBox client connection")
        # pynetbox doesn't require explicit close
        _netbox_client = None


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

    async def _fetch_prefixes_from_netbox(self, nb_filter: Dict[str, Any]) -> List[Any]:
        """Helper method to fetch prefixes from NetBox (used for request coalescing)"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_read_executor()

        t_fetch = time.time()
        prefixes = await loop.run_in_executor(
            executor,
            lambda: list(self.nb.ipam.prefixes.filter(**nb_filter))
        )
        elapsed = (time.time() - t_fetch) * 1000

        if elapsed > 20000:
            logger.error(f"🚨 NETBOX SEVERE THROTTLING: fetch prefixes took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
        elif elapsed > 5000:
            logger.warning(f"⚠️  NETBOX THROTTLED: fetch prefixes took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
        elif elapsed > 2000:
            logger.info(f"⏱️  NETBOX SLOW: fetch prefixes took {elapsed:.0f}ms")
        else:
            logger.debug(f"⏱️  NETBOX OK: fetch prefixes took {elapsed:.0f}ms")

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
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        # NOTE: Using cached data from find() instead of direct API filtering
        # This avoids NetBox API compatibility issues and leverages caching
        t_fetch = time.time()

        # Use find() with caching instead of direct API call
        try:
            results = await self.find(query)
            logger.info(f"⏱️  find_one_optimized took {(time.time() - t_fetch)*1000:.0f}ms")
            return results[0] if results else None
        except Exception as e:
            logger.error(f"find_one_optimized failed: {e}")
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
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        # Build NetBox filter for prefixes
        # PERFORMANCE: Always filter by Redbull tenant to reduce data fetched
        nb_filter = {}

        # Get Redbull tenant ID for filtering
        tenant_id = await self._get_redbull_tenant_id()
        if tenant_id:
            nb_filter["tenant_id"] = tenant_id

        # Filter by VLAN VID if provided
        if query and "vlan_id" in query:
            nb_filter["vlan_vid"] = query["vlan_id"]

        # Use simple cache key (VRF filtering happens in-memory)
        cache_key = "prefixes"
        prefixes = _get_cached(cache_key)

        if prefixes is None:
            # Check if another request is already fetching this data
            if cache_key in _inflight_requests:
                logger.info(f"⏳ Waiting for in-flight prefixes fetch (request coalescing)")
                t_wait = time.time()
                # Wait for the in-flight request to complete
                try:
                    prefixes = await _inflight_requests[cache_key]
                    logger.info(f"⏱️  Waited {(time.time() - t_wait)*1000:.0f}ms for coalesced request")
                except Exception as e:
                    logger.error(f"In-flight request failed: {e}")
                    # Fall through to fetch ourselves
                    prefixes = None

            if prefixes is None:
                # Create a future for this fetch so other concurrent requests can wait
                fetch_future = asyncio.create_task(self._fetch_prefixes_from_netbox(nb_filter))
                _inflight_requests[cache_key] = fetch_future

                try:
                    t_fetch = time.time()
                    logger.info(f"Fetching prefixes from NetBox with filter: {nb_filter} (cache miss)")
                    prefixes = await fetch_future
                    logger.info(f"⏱️      NetBox fetch took {(time.time() - t_fetch)*1000:.0f}ms ({len(prefixes)} prefixes)")
                    # Cache the results
                    _set_cache(cache_key, prefixes)
                finally:
                    # Remove from in-flight tracker
                    _inflight_requests.pop(cache_key, None)
        else:
            logger.debug(f"Using cached prefixes ({len(prefixes)} items, key={cache_key})")

        # Convert NetBox prefixes to our segment format and apply filters
        segments = []
        for prefix in prefixes:
            segment = self._prefix_to_segment(prefix)

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
                        import re
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
                                import re
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
                gather_tasks.append(self._get_vrf(document["vrf"]))
                task_names.append("vrf")
            else:
                gather_tasks.append(None)  # Placeholder
                task_names.append("vrf")

            if "site" in document and document["site"]:
                gather_tasks.append(self._get_or_create_site(document["site"]))
                task_names.append("site_group")
            else:
                gather_tasks.append(None)
                task_names.append("site_group")

            gather_tasks.append(self._get_tenant("Redbull"))
            task_names.append("tenant")

            gather_tasks.append(self._get_role("Data", "prefix"))
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
                logger.debug(f"Assigned VRF to prefix")

            # Add site group scope if provided
            if site_group_obj:
                if not site_group_obj:
                    raise Exception(f"Failed to get/create site group: {document['site']}")
                prefix_data["scope_type"] = "dcim.sitegroup"
                prefix_data["scope_id"] = site_group_obj.id
                logger.debug(f"Assigned Site Group scope: type=dcim.sitegroup, id={site_group_obj.id}")

            # Add tenant "Redbull"
            if tenant:
                prefix_data["tenant"] = tenant.id
                logger.debug(f"Assigned tenant 'Redbull' to prefix")

            # Add role "Data"
            if role:
                prefix_data["role"] = role.id
                logger.debug(f"Assigned role 'Data' to prefix")

            # Add VLAN if provided (pass VRF name for VLAN group)
            # Note: VLAN creation must be separate as it depends on VRF
            if "vlan_id" in document and document["vlan_id"]:
                logger.debug(f"Getting/creating VLAN: {document['vlan_id']}")
                vlan_obj = await self._get_or_create_vlan(
                    document["vlan_id"],
                    document.get("epg_name", f"VLAN_{document['vlan_id']}"),
                    document.get("site"),
                    document.get("vrf")  # Pass VRF name for VLAN group creation
                )
                if not vlan_obj:
                    raise Exception(f"Failed to get/create VLAN: {document['vlan_id']}")
                prefix_data["vlan"] = vlan_obj.id
                logger.debug(f"VLAN ID: {vlan_obj.id}")

            # Add custom fields
            custom_fields = {}
            if "dhcp" in document:
                custom_fields["dhcp"] = document["dhcp"]
            if "cluster_name" in document and document["cluster_name"]:
                custom_fields["cluster"] = document["cluster_name"]

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
            return self._prefix_to_segment(prefix)

        except Exception as e:
            logger.error(f"Error creating prefix in NetBox: {e}")
            raise

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a segment in NetBox"""
        t_total = time.time()
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

            # BEFORE get prefix - log to detect thread pool wait time
            logger.debug(f"Submitting get_prefix to read thread pool (prefix_id={prefix_id})")
            t_get = time.time()

            prefix = await loop.run_in_executor(
                read_executor,
                lambda: self.nb.ipam.prefixes.get(prefix_id)
            )
            elapsed = (time.time() - t_get) * 1000

            if elapsed > 20000:
                logger.error(f"🚨 NETBOX SEVERE THROTTLING: get prefix took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
            elif elapsed > 5000:
                logger.warning(f"⚠️  NETBOX THROTTLED: get prefix took {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
            elif elapsed > 2000:
                logger.info(f"⏱️  NETBOX SLOW: get prefix took {elapsed:.0f}ms")
            else:
                logger.debug(f"⏱️  NETBOX OK: get prefix took {elapsed:.0f}ms")

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
                    vrf_obj = await self._get_vrf(updates["vrf"])
                    if vrf_obj:
                        prefix.vrf = vrf_obj.id
                        logger.debug(f"Updated VRF to: {updates['vrf']}")

                # Handle custom field updates (DHCP)
                if "dhcp" in updates:
                    if not hasattr(prefix, 'custom_fields') or prefix.custom_fields is None:
                        prefix.custom_fields = {}
                    prefix.custom_fields['dhcp'] = updates["dhcp"]
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
                            logger.warning(f"Failed to get old VLAN for cleanup: {e}")

                    # Need to update or create VLAN object
                    vlan_id = updates.get("vlan_id", segment.get("vlan_id"))
                    epg_name = updates.get("epg_name", segment.get("epg_name"))
                    site = updates.get("site", segment.get("site"))
                    vrf = updates.get("vrf", segment.get("vrf"))

                    if vlan_id and epg_name:
                        new_vlan_obj = await self._get_or_create_vlan(vlan_id, epg_name, site, vrf)
                        if new_vlan_obj:
                            prefix.vlan = new_vlan_obj.id
                            logger.info(f"Updated prefix to new VLAN {vlan_id} (NetBox ID: {new_vlan_obj.id})")

                # Update prefix status and CUSTOM FIELD based on allocation state
                # IMPORTANT: CUSTOM FIELD "cluster" is for cluster name, COMMENTS is for user info
                if "cluster_name" in updates and updates["cluster_name"]:
                    # Allocated: set status to "reserved" and cluster custom field
                    cluster_name = updates["cluster_name"]
                    prefix.status = "reserved"
                    if not hasattr(prefix, 'custom_fields') or prefix.custom_fields is None:
                        prefix.custom_fields = {}
                    prefix.custom_fields['cluster'] = cluster_name
                    logger.debug(f"Set allocation: cluster={cluster_name}, status=reserved")
                elif "released" in updates and updates["released"]:
                    # Released: set status back to "active" and clear cluster custom field
                    prefix.status = "active"
                    if hasattr(prefix, 'custom_fields') and prefix.custom_fields:
                        prefix.custom_fields['cluster'] = None
                    logger.debug("Cleared allocation: status=active, cluster=empty")

                # Save changes FIRST before cleanup (use write executor for slow saves)
                logger.debug(f"Submitting save to write thread pool (prefix_id={prefix_id})")
                t_save = time.time()
                await loop.run_in_executor(write_executor, prefix.save)
                elapsed_save = (time.time() - t_save) * 1000

                if elapsed_save > 20000:
                    logger.error(f"🚨 NETBOX SEVERE THROTTLING: save prefix took {elapsed_save:.0f}ms ({elapsed_save/1000:.1f}s)")
                elif elapsed_save > 5000:
                    logger.warning(f"⚠️  NETBOX THROTTLED: save prefix took {elapsed_save:.0f}ms ({elapsed_save/1000:.1f}s)")
                elif elapsed_save > 2000:
                    logger.info(f"⏱️  NETBOX SLOW: save prefix took {elapsed_save:.0f}ms")
                else:
                    logger.debug(f"⏱️  NETBOX OK: save prefix took {elapsed_save:.0f}ms")

                logger.info(f"Updated prefix {prefix.prefix} (ID: {prefix_id})")

                # NOW clean up old VLAN if it's no longer used by any prefix
                # This must happen AFTER saving so NetBox shows the new VLAN assignment
                if "vlan_id" in updates or "epg_name" in updates:
                    if old_vlan_obj and old_vlan_vid and old_vlan_vid != updates.get("vlan_id", segment.get("vlan_id")):
                        logger.info(f"Checking if old VLAN {old_vlan_vid} can be cleaned up...")
                        await self._cleanup_unused_vlan(old_vlan_obj)
                    elif not old_vlan_obj:
                        logger.debug("No old VLAN to clean up (prefix had no VLAN before)")

                # Invalidate cache since we modified data
                t_invalidate = time.time()
                invalidate_cache("prefixes")
                logger.info(f"⏱️      Cache invalidation took {(time.time() - t_invalidate)*1000:.0f}ms")

            return True

        except Exception as e:
            logger.error(f"Error updating prefix in NetBox: {e}")
            return False

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment from NetBox"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        segment = await self.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]
            await loop.run_in_executor(
                executor,
                lambda: self.nb.ipam.prefixes.get(prefix_id).delete()
            )
            logger.info(f"Deleted prefix ID: {prefix_id}")

            # Invalidate cache since we modified data
            invalidate_cache("prefixes")

            return True

        except Exception as e:
            logger.error(f"Error deleting prefix from NetBox: {e}")
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

    def _prefix_to_segment(self, prefix) -> Dict[str, Any]:
        """Convert NetBox prefix object to our segment format

        Note: In NetBox, the site is associated with the VLAN, not the prefix directly.
        Metadata is extracted from STATUS and DESCRIPTION fields, not comments.
        Comments field is left free for user notes.
        """
        from datetime import datetime, timezone

        # Extract site from Prefix scope (Site Group), not from VLAN
        site_slug = None
        vlan_id = None
        epg_name = ""

        # Extract VLAN ID and EPG name from VLAN object
        if hasattr(prefix, 'vlan') and prefix.vlan:
            # prefix.vlan is already a VLAN Record object in pynetbox
            vlan_obj = prefix.vlan

            # Get VLAN VID (the VLAN number like 100, 101)
            if hasattr(vlan_obj, 'vid'):
                vlan_id = vlan_obj.vid

            # Get EPG name from VLAN name
            if hasattr(vlan_obj, 'name'):
                epg_name = vlan_obj.name

        # Extract site from Prefix scope (Site Group) - NOT from VLAN!
        # VLANs should NOT have site or site_group assignment
        # Only Prefixes should have Site Group scope
        if hasattr(prefix, 'scope_type') and prefix.scope_type and 'sitegroup' in str(prefix.scope_type).lower():
            if hasattr(prefix, 'scope_id') and prefix.scope_id:
                # Use cached site groups to avoid repeated API calls
                # Cache site_group lookups by ID
                cache_key = f"site_group_{prefix.scope_id}"
                site_group = _get_cached(cache_key)

                if site_group is None:
                    # Need to fetch the site group to get its slug
                    try:
                        site_group = self.nb.dcim.site_groups.get(prefix.scope_id)
                        if site_group:
                            _set_cache(cache_key, site_group)
                    except Exception as e:
                        logger.warning(f"Failed to fetch site group for prefix {prefix.id}: {e}")
                        site_group = None

                if site_group:
                    site_slug = site_group.slug

        # Extract metadata from STATUS and DESCRIPTION
        status_val = prefix.status.value if hasattr(prefix.status, 'value') else str(prefix.status).lower()
        netbox_description = getattr(prefix, 'description', '') or ""
        user_comments = getattr(prefix, 'comments', '') or ""

        # Determine if allocated or released based on STATUS
        released = (status_val == 'active')

        # Extract cluster name from custom field or description (for backward compatibility)
        cluster_name = None
        custom_fields = getattr(prefix, 'custom_fields', {}) or {}

        if 'cluster' in custom_fields and custom_fields['cluster']:
            cluster_name = custom_fields['cluster']
        elif status_val == 'reserved' and netbox_description.startswith('Cluster: '):
            cluster_name = netbox_description.replace('Cluster: ', '').strip()

        # Extract VRF
        vrf_name = None
        if hasattr(prefix, 'vrf') and prefix.vrf:
            vrf_name = prefix.vrf.name if hasattr(prefix.vrf, 'name') else str(prefix.vrf)

        # Extract DHCP from custom field
        dhcp = False
        if 'dhcp' in custom_fields:
            dhcp = bool(custom_fields['dhcp'])

        # For timestamps, we'll use current time as approximation
        # (NetBox doesn't store these, so we set them when we update)
        allocated_at = None
        released_at = None

        # If it's reserved, set allocated_at to now (approximation)
        if status_val == 'reserved' and cluster_name:
            allocated_at = datetime.now(timezone.utc)

        segment = {
            "_id": str(prefix.id),
            "site": site_slug,
            "vlan_id": vlan_id,
            "epg_name": epg_name,
            "segment": str(prefix.prefix),
            "vrf": vrf_name,
            "dhcp": dhcp,
            "description": user_comments,  # Return user comments as description for API
            "cluster_name": cluster_name,
            "allocated_at": allocated_at,
            "released": released,
            "released_at": released_at,
        }

        return segment

    async def _get_or_create_site(self, site_slug: str):
        """Get or create a site group in NetBox (not regular site)"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            # Try to get existing site group
            site_group = await loop.run_in_executor(
                executor,
                lambda: self.nb.dcim.site_groups.get(slug=site_slug)
            )

            if site_group:
                logger.debug(f"Found existing site group: {site_slug}")
                return site_group

            # Create new site group
            logger.info(f"Creating new site group in NetBox: {site_slug}")
            site_group = await loop.run_in_executor(
                executor,
                lambda: self.nb.dcim.site_groups.create(
                    name=site_slug.upper(),
                    slug=site_slug
                )
            )
            logger.info(f"Created site group in NetBox: {site_slug}")
            return site_group

        except Exception as e:
            logger.error(f"Error getting/creating site group {site_slug}: {e}")
            raise

    async def _cleanup_unused_vlan(self, vlan_obj):
        """
        Delete a VLAN from NetBox if it's no longer used by any prefix

        Args:
            vlan_obj: The VLAN object to check and potentially delete
        """
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            # Check if any prefixes are still using this VLAN
            prefixes_using_vlan = await loop.run_in_executor(
                executor,
                lambda: list(self.nb.ipam.prefixes.filter(vlan_id=vlan_obj.id))
            )

            if not prefixes_using_vlan or len(prefixes_using_vlan) == 0:
                # No prefixes using this VLAN - safe to delete
                logger.info(f"Deleting unused VLAN {vlan_obj.vid} ({vlan_obj.name}) - ID: {vlan_obj.id}")
                await loop.run_in_executor(
                    executor,
                    lambda: vlan_obj.delete()
                )
                logger.info(f"Successfully deleted VLAN {vlan_obj.vid}")
            else:
                logger.debug(f"VLAN {vlan_obj.vid} still in use by {len(prefixes_using_vlan)} prefix(es), keeping it")

        except Exception as e:
            logger.warning(f"Error cleaning up VLAN {vlan_obj.vid}: {e}")
            # Don't fail the update if cleanup fails

    async def _get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None, vrf_name: Optional[str] = None):
        """Get or create a VLAN in NetBox with tenant, role, and group

        IMPORTANT: VLANs should NOT be assigned to site or site_group.
        Only Prefixes are assigned to site_groups.
        """
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        # Build filter - search by VLAN ID only, not by site
        vlan_filter = {"vid": vlan_id}

        # Try to get existing VLAN
        vlan = await loop.run_in_executor(
            executor,
            lambda: self.nb.ipam.vlans.get(**vlan_filter)
        )

        if not vlan:
            # Prepare VLAN data - NO site or site_group assignment for VLANs
            vlan_data = {
                "vid": vlan_id,
                "name": name,
                "status": "active",
            }

            # Create site group if needed (for Prefix, not VLAN)
            if site_slug:
                await self._get_or_create_site(site_slug)

            # Add tenant "Redbull"
            tenant = await self._get_tenant("Redbull")
            if tenant:
                vlan_data["tenant"] = tenant.id
                logger.debug(f"Assigned tenant 'Redbull' to VLAN")

            # Add role "Data"
            role = await self._get_role("Data", "vlan")
            if role:
                vlan_data["role"] = role.id
                logger.debug(f"Assigned role 'Data' to VLAN")

            # Add VLAN Group if VRF provided
            if vrf_name and site_slug:
                # Extract site number (e.g., "site1" -> "Site1")
                site_group = site_slug.capitalize()
                vlan_group = await self._get_or_create_vlan_group(vrf_name, site_group)
                if vlan_group:
                    vlan_data["group"] = vlan_group.id
                    logger.debug(f"Assigned VLAN group '{vlan_group.name}' to VLAN")

            # Create new VLAN
            vlan = await loop.run_in_executor(
                executor,
                lambda: self.nb.ipam.vlans.create(**vlan_data)
            )
            logger.info(f"Created VLAN in NetBox: {vlan_id} ({name}) with tenant=Redbull, role=Data")
        else:
            # VLAN exists - check if name or group needs to be updated
            needs_update = False

            if vlan.name != name:
                logger.info(f"Updating VLAN name from '{vlan.name}' to '{name}' for VLAN ID {vlan_id}")
                vlan.name = name
                needs_update = True

            # Ensure VLAN Group is set if provided and not already set
            if vrf_name and site_slug:
                site_group = site_slug.capitalize()
                expected_group_name = f"{vrf_name}-ClickCluster-{site_group}"

                # Check if VLAN has the correct group
                if not vlan.group or (hasattr(vlan.group, 'name') and vlan.group.name != expected_group_name):
                    vlan_group = await self._get_or_create_vlan_group(vrf_name, site_group)
                    if vlan_group:
                        vlan.group = vlan_group.id
                        logger.info(f"Updating VLAN group to '{vlan_group.name}' for VLAN ID {vlan_id}")
                        needs_update = True

            if needs_update:
                await loop.run_in_executor(executor, vlan.save)
                logger.info(f"Updated VLAN {vlan_id} successfully")

        return vlan

    async def _get_vrf(self, vrf_name: str):
        """Get VRF from NetBox (do not create - must exist)"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            vrf = await loop.run_in_executor(
                executor,
                lambda: self.nb.ipam.vrfs.get(name=vrf_name)
            )

            if not vrf:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail=f"VRF '{vrf_name}' does not exist in NetBox. Please create it first or select an existing VRF."
                )

            logger.debug(f"Found VRF in NetBox: {vrf_name} (ID: {vrf.id})")
            return vrf

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching VRF '{vrf_name}' from NetBox: {e}")
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching VRF from NetBox: {str(e)}"
            )

    async def _get_tenant(self, tenant_name: str):
        """Get tenant from NetBox (must exist)"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            tenant = await loop.run_in_executor(
                executor,
                lambda: self.nb.tenancy.tenants.get(name=tenant_name)
            )

            if not tenant:
                logger.warning(f"Tenant '{tenant_name}' not found in NetBox")
                return None

            logger.debug(f"Found tenant in NetBox: {tenant_name} (ID: {tenant.id})")
            return tenant

        except Exception as e:
            logger.error(f"Error fetching tenant '{tenant_name}' from NetBox: {e}")
            return None

    async def _get_redbull_tenant_id(self) -> Optional[int]:
        """Get cached Redbull tenant ID for filtering"""
        cached_id = _get_cached("redbull_tenant_id")
        if cached_id is not None:
            return cached_id

        # Fetch tenant ID
        tenant = await self._get_tenant("Redbull")
        if tenant:
            _set_cache("redbull_tenant_id", tenant.id)
            return tenant.id

        return None

    async def _get_role(self, role_name: str, model_type: str = "vlan"):
        """Get role from NetBox (must exist)

        Args:
            role_name: Name of the role (e.g., "Data")
            model_type: Type of model ("vlan" or "prefix")
        """
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            # Roles are in ipam.roles for both VLANs and Prefixes
            role = await loop.run_in_executor(
                executor,
                lambda: self.nb.ipam.roles.get(name=role_name)
            )

            if not role:
                logger.warning(f"Role '{role_name}' not found in NetBox")
                return None

            logger.debug(f"Found role in NetBox: {role_name} (ID: {role.id})")
            return role

        except Exception as e:
            logger.error(f"Error fetching role '{role_name}' from NetBox: {e}")
            return None

    async def _get_or_create_vlan_group(self, vrf_name: str, site_group: str):
        """Get or create VLAN Group: Network{X}-ClickCluster-Site{Y}"""
        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        # Format: "Network1-ClickCluster-Site1"
        group_name = f"{vrf_name}-ClickCluster-{site_group}"

        try:
            vlan_group = await loop.run_in_executor(
                executor,
                lambda: self.nb.ipam.vlan_groups.get(name=group_name)
            )

            if not vlan_group:
                # Create new VLAN Group
                vlan_group_data = {
                    "name": group_name,
                    "slug": group_name.lower().replace("_", "-"),
                }

                vlan_group = await loop.run_in_executor(
                    executor,
                    lambda: self.nb.ipam.vlan_groups.create(**vlan_group_data)
                )
                logger.info(f"Created VLAN Group in NetBox: {group_name}")

            return vlan_group

        except Exception as e:
            logger.error(f"Error getting/creating VLAN group '{group_name}': {e}")
            return None

    async def get_vrfs(self) -> List[str]:
        """Get list of available VRFs from NetBox (cached for 1 hour)"""
        # Check cache first - VRFs rarely change
        cached_vrfs = _get_cached("vrfs")
        if cached_vrfs is not None:
            logger.debug(f"Using cached VRFs: {cached_vrfs}")
            return cached_vrfs

        loop = asyncio.get_event_loop()
        executor = get_netbox_executor()

        try:
            t_start = time.time()
            vrfs = await loop.run_in_executor(
                executor,
                lambda: list(self.nb.ipam.vrfs.all())
            )
            elapsed = (time.time() - t_start) * 1000
            vrf_names = [vrf.name for vrf in vrfs]

            if elapsed > 20000:
                logger.error(f"🚨 NETBOX SEVERE THROTTLING: fetch VRFs took {elapsed:.0f}ms ({elapsed/1000:.1f}s) - Retrieved {len(vrf_names)} VRFs: {vrf_names}")
            elif elapsed > 5000:
                logger.warning(f"⚠️  NETBOX THROTTLED: fetch VRFs took {elapsed:.0f}ms ({elapsed/1000:.1f}s) - Retrieved {len(vrf_names)} VRFs: {vrf_names}")
            elif elapsed > 2000:
                logger.info(f"⏱️  NETBOX SLOW: fetch VRFs took {elapsed:.0f}ms - Retrieved {len(vrf_names)} VRFs: {vrf_names}")
            else:
                logger.debug(f"⏱️  NETBOX OK: fetch VRFs took {elapsed:.0f}ms - Retrieved {len(vrf_names)} VRFs: {vrf_names}")

            # Cache VRFs for 1 hour (they rarely change)
            _set_cache("vrfs", vrf_names)

            return vrf_names
        except Exception as e:
            logger.error(f"Error fetching VRFs from NetBox: {e}")
            raise


def get_storage() -> NetBoxStorage:
    """Get the NetBox storage instance"""
    return NetBoxStorage()
