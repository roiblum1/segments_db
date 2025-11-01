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

from ..config.settings import NETBOX_URL, NETBOX_TOKEN, NETBOX_SSL_VERIFY

logger = logging.getLogger(__name__)

# Global NetBox API client
_netbox_client: Optional[pynetbox.api] = None

# Simple in-memory cache with TTL
_cache = {
    "prefixes": {"data": None, "timestamp": 0, "ttl": 30},  # 30 seconds TTL
    "vlans": {"data": None, "timestamp": 0, "ttl": 60},      # 60 seconds TTL
}


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
    """Initialize NetBox storage - verify connection"""
    try:
        nb = get_netbox_client()

        # Test connection by getting status
        loop = asyncio.get_event_loop()
        status = await loop.run_in_executor(None, lambda: nb.status())

        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")
        logger.info(f"NetBox URL: {NETBOX_URL}")

    except Exception as e:
        logger.error(f"Failed to connect to NetBox: {e}")
        raise


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

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
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
        loop = asyncio.get_event_loop()

        # Build NetBox filter for prefixes
        # Note: We can't filter by site at the prefix level since prefixes don't have sites
        # We'll fetch all prefixes and filter in-memory based on VLAN's site
        nb_filter = {}

        # We can only filter by VLAN VID at the API level
        if query and "vlan_id" in query:
            nb_filter["vlan_vid"] = query["vlan_id"]

        # Try to get prefixes from cache
        cache_key = "prefixes"
        prefixes = _get_cached(cache_key)

        if prefixes is None:
            # Cache miss - fetch from NetBox
            logger.info("Fetching prefixes from NetBox (cache miss)")
            if nb_filter:
                prefixes = await loop.run_in_executor(
                    None,
                    lambda: list(self.nb.ipam.prefixes.filter(**nb_filter))
                )
            else:
                # Fetch all prefixes
                prefixes = await loop.run_in_executor(
                    None,
                    lambda: list(self.nb.ipam.prefixes.all())
                )
            # Cache the results
            _set_cache(cache_key, prefixes)
        else:
            logger.debug(f"Using cached prefixes ({len(prefixes)} items)")

        # Convert NetBox prefixes to our segment format and apply filters
        segments = []
        for prefix in prefixes:
            segment = self._prefix_to_segment(prefix)

            # Apply in-memory filters
            if query:
                # Site filter - check the site from the VLAN
                if "site" in query and segment.get("site") != query["site"]:
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

        try:
            logger.debug(f"Creating NetBox prefix for document: {document}")

            # Prepare prefix data
            # DESCRIPTION will be used for cluster name when allocated
            # COMMENTS will store the user's info (DHCP, Gateway, etc.)
            prefix_data = {
                "prefix": document["segment"],
                "description": "",  # Empty initially, will show cluster name when allocated
                "comments": document.get("description", ""),  # User info goes in comments
                "status": "active",
            }

            # Add site if provided
            if "site" in document and document["site"]:
                logger.debug(f"Getting/creating site: {document['site']}")
                site_obj = await self._get_or_create_site(document["site"])
                if not site_obj:
                    raise Exception(f"Failed to get/create site: {document['site']}")
                prefix_data["site"] = site_obj.id
                logger.debug(f"Site ID: {site_obj.id}")

            # Add VLAN if provided
            if "vlan_id" in document and document["vlan_id"]:
                logger.debug(f"Getting/creating VLAN: {document['vlan_id']}")
                vlan_obj = await self._get_or_create_vlan(
                    document["vlan_id"],
                    document.get("epg_name", f"VLAN_{document['vlan_id']}"),
                    document.get("site")
                )
                if not vlan_obj:
                    raise Exception(f"Failed to get/create VLAN: {document['vlan_id']}")
                prefix_data["vlan"] = vlan_obj.id
                logger.debug(f"VLAN ID: {vlan_obj.id}")

            # Note: Comments already populated with user info from description field above
            # Description will show cluster name when allocated

            # Create prefix in NetBox
            logger.debug(f"Creating prefix with data: {prefix_data}")
            prefix = await loop.run_in_executor(
                None,
                lambda: self.nb.ipam.prefixes.create(**prefix_data)
            )

            logger.info(f"Created prefix in NetBox: {prefix.prefix} (ID: {prefix.id})")
            logger.debug(f"Created prefix site: {getattr(prefix, 'site', 'NO-SITE')}")

            # Invalidate cache since we modified data
            invalidate_cache("prefixes")

            # Return in our format
            return self._prefix_to_segment(prefix)

        except Exception as e:
            logger.error(f"Error creating prefix in NetBox: {e}")
            raise

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a segment in NetBox"""
        loop = asyncio.get_event_loop()

        # Find the prefix
        segment = await self.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]
            prefix = await loop.run_in_executor(
                None,
                lambda: self.nb.ipam.prefixes.get(prefix_id)
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
                                None,
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

                    if vlan_id and epg_name:
                        new_vlan_obj = await self._get_or_create_vlan(vlan_id, epg_name, site)
                        if new_vlan_obj:
                            prefix.vlan = new_vlan_obj.id
                            logger.info(f"Updated prefix to new VLAN {vlan_id} (NetBox ID: {new_vlan_obj.id})")

                # Update prefix status and DESCRIPTION based on allocation state
                # IMPORTANT: DESCRIPTION is for cluster name, COMMENTS is for user info
                if "cluster_name" in updates and updates["cluster_name"]:
                    # Allocated: set status to "reserved" and description to cluster name
                    cluster_name = updates["cluster_name"]
                    prefix.status = "reserved"
                    prefix.description = f"Cluster: {cluster_name}"
                    logger.debug(f"Set allocation: cluster={cluster_name}, status=reserved")
                elif "released" in updates and updates["released"]:
                    # Released: set status back to "active" and clear DESCRIPTION (not comments!)
                    prefix.status = "active"
                    prefix.description = ""  # Empty when available
                    logger.debug("Cleared allocation: status=active, description=empty")

                # Save changes FIRST before cleanup
                await loop.run_in_executor(None, prefix.save)
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
                invalidate_cache("prefixes")

            return True

        except Exception as e:
            logger.error(f"Error updating prefix in NetBox: {e}")
            return False

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment from NetBox"""
        loop = asyncio.get_event_loop()

        segment = await self.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]
            await loop.run_in_executor(
                None,
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
        # Find all matching segments
        segments = await self.find(query)

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

        # Return updated segment
        return await self.find_one({"_id": segment["_id"]})

    def _prefix_to_segment(self, prefix) -> Dict[str, Any]:
        """Convert NetBox prefix object to our segment format

        Note: In NetBox, the site is associated with the VLAN, not the prefix directly.
        Metadata is extracted from STATUS and DESCRIPTION fields, not comments.
        Comments field is left free for user notes.
        """
        from datetime import datetime, timezone

        # Extract site and VLAN ID from VLAN object
        site_slug = None
        vlan_id = None
        epg_name = ""

        if hasattr(prefix, 'vlan') and prefix.vlan:
            # prefix.vlan is already a VLAN Record object in pynetbox
            vlan_obj = prefix.vlan

            # Get VLAN VID (the VLAN number like 100, 101)
            if hasattr(vlan_obj, 'vid'):
                vlan_id = vlan_obj.vid

            # Get EPG name from VLAN name
            if hasattr(vlan_obj, 'name'):
                epg_name = vlan_obj.name

            # Get site from VLAN
            if hasattr(vlan_obj, 'site') and vlan_obj.site:
                site_slug = vlan_obj.site.slug if hasattr(vlan_obj.site, 'slug') else None

        # Extract metadata from STATUS and DESCRIPTION
        status_val = prefix.status.value if hasattr(prefix.status, 'value') else str(prefix.status).lower()
        netbox_description = getattr(prefix, 'description', '') or ""
        user_comments = getattr(prefix, 'comments', '') or ""

        # Determine if allocated or released based on STATUS
        released = (status_val == 'active')

        # Extract cluster name from description if allocated
        cluster_name = None
        if status_val == 'reserved' and netbox_description.startswith('Cluster: '):
            cluster_name = netbox_description.replace('Cluster: ', '').strip()

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
            "description": user_comments,  # Return user comments as description for API
            "cluster_name": cluster_name,
            "allocated_at": allocated_at,
            "released": released,
            "released_at": released_at,
        }

        return segment

    async def _get_or_create_site(self, site_slug: str):
        """Get or create a site in NetBox"""
        loop = asyncio.get_event_loop()

        try:
            # Try to get existing site
            site = await loop.run_in_executor(
                None,
                lambda: self.nb.dcim.sites.get(slug=site_slug)
            )

            if site:
                return site

            # Create new site
            logger.info(f"Creating new site in NetBox: {site_slug}")
            site = await loop.run_in_executor(
                None,
                lambda: self.nb.dcim.sites.create(
                    name=site_slug.upper(),
                    slug=site_slug,
                    status="active"
                )
            )
            logger.info(f"Created site in NetBox: {site_slug}")
            return site

        except Exception as e:
            logger.error(f"Error getting/creating site {site_slug}: {e}")
            raise

    async def _cleanup_unused_vlan(self, vlan_obj):
        """
        Delete a VLAN from NetBox if it's no longer used by any prefix

        Args:
            vlan_obj: The VLAN object to check and potentially delete
        """
        loop = asyncio.get_event_loop()

        try:
            # Check if any prefixes are still using this VLAN
            prefixes_using_vlan = await loop.run_in_executor(
                None,
                lambda: list(self.nb.ipam.prefixes.filter(vlan_id=vlan_obj.id))
            )

            if not prefixes_using_vlan or len(prefixes_using_vlan) == 0:
                # No prefixes using this VLAN - safe to delete
                logger.info(f"Deleting unused VLAN {vlan_obj.vid} ({vlan_obj.name}) - ID: {vlan_obj.id}")
                await loop.run_in_executor(
                    None,
                    lambda: vlan_obj.delete()
                )
                logger.info(f"Successfully deleted VLAN {vlan_obj.vid}")
            else:
                logger.debug(f"VLAN {vlan_obj.vid} still in use by {len(prefixes_using_vlan)} prefix(es), keeping it")

        except Exception as e:
            logger.warning(f"Error cleaning up VLAN {vlan_obj.vid}: {e}")
            # Don't fail the update if cleanup fails

    async def _get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None):
        """Get or create a VLAN in NetBox"""
        loop = asyncio.get_event_loop()

        # Build filter
        vlan_filter = {"vid": vlan_id}
        if site_slug:
            vlan_filter["site"] = site_slug

        # Try to get existing VLAN
        vlan = await loop.run_in_executor(
            None,
            lambda: self.nb.ipam.vlans.get(**vlan_filter)
        )

        if not vlan:
            # Prepare VLAN data
            vlan_data = {
                "vid": vlan_id,
                "name": name,
                "status": "active",
            }

            if site_slug:
                site = await self._get_or_create_site(site_slug)
                vlan_data["site"] = site.id

            # Create new VLAN
            vlan = await loop.run_in_executor(
                None,
                lambda: self.nb.ipam.vlans.create(**vlan_data)
            )
            logger.info(f"Created VLAN in NetBox: {vlan_id} ({name})")
        else:
            # VLAN exists - check if name needs to be updated
            if vlan.name != name:
                logger.info(f"Updating VLAN name from '{vlan.name}' to '{name}' for VLAN ID {vlan_id}")
                vlan.name = name
                await loop.run_in_executor(None, vlan.save)
                logger.info(f"Updated VLAN name to '{name}' for VLAN ID {vlan_id}")

        return vlan


def get_storage() -> NetBoxStorage:
    """Get the NetBox storage instance"""
    return NetBoxStorage()
