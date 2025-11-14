import logging
import time
from typing import Optional, List, Dict, Any

from ..config.settings import SITES, STORAGE_BACKEND
from .time_utils import get_current_utc

logger = logging.getLogger(__name__)

# Dynamic storage import based on configuration
def get_storage():
    """Get storage backend based on configuration"""
    if STORAGE_BACKEND == "mysql":
        from ..database.mysql_storage import get_storage as get_mysql_storage
        return get_mysql_storage()
    else:
        from ..database.netbox_storage import get_storage as get_netbox_storage
        return get_netbox_storage()

class DatabaseUtils:
    """Utility class for database operations"""
    
    @staticmethod
    async def find_existing_allocation(cluster_name: str, site: str) -> Optional[Dict[str, Any]]:
        """Find existing allocation for a cluster at a site
        Supports both single clusters and shared segments (comma-separated)

        Uses optimized NetBox API filtering to reduce data transfer
        """
        storage = get_storage()

        # Use optimized find for exact match first
        exact_match = await storage.find_one_optimized({
            "cluster_name": cluster_name,
            "site": site,
            "released": False
        })
        if exact_match:
            return exact_match

        # For regex search (shared segments), we still need find_one
        # but this is rare, so less impact
        shared_match = await storage.find_one({
            "cluster_name": {"$regex": f"(^|,){cluster_name}(,|$)"},
            "site": site,
            "released": False
        })
        return shared_match
    
    @staticmethod
    async def find_and_allocate_segment(site: str, cluster_name: str, vrf: str) -> Optional[Dict[str, Any]]:
        """Atomically find and allocate an available segment for a site
        Supports all subnet sizes (/24, /21, /16, etc.) for cluster allocation

        Args:
            site: Site to allocate from
            cluster_name: Name of cluster to allocate to
            vrf: VRF/Network to filter by (e.g., "Network1", "Network2") - REQUIRED
        """
        storage = get_storage()
        allocation_time = get_current_utc()

        # Build query filter with required VRF
        query_filter = {
            "site": site,
            "cluster_name": None,
            "vrf": vrf
        }

        logger.info(f"Allocating from site={site}, VRF={vrf}")

        # Use find_one_and_update for atomic operation - prevents race conditions
        # Find segments that are either never allocated (released: False, cluster_name: None)
        # OR have been released (released: True, cluster_name: None)
        # Sort by vlan_id to always allocate the smallest available VLAN ID first
        t1 = time.time()
        result = await storage.find_one_and_update(
            query_filter,
            {
                "$set": {
                    "cluster_name": cluster_name,
                    "allocated_at": allocation_time,
                    "released": False,
                    "released_at": None
                }
            },
            sort=[("vlan_id", 1)]  # Sort by vlan_id ascending to get smallest first
        )
        logger.info(f"⏱️  storage.find_one_and_update took {(time.time() - t1)*1000:.0f}ms")
        return result
    
    @staticmethod
    async def find_available_segment(site: str) -> Optional[Dict[str, Any]]:
        """Find an available segment for a site (kept for backward compatibility)
        Returns any available segment regardless of subnet size
        """
        storage = get_storage()
        return await storage.find_one({
            "site": site,
            "cluster_name": None
            # Allow both released: False (never allocated) and released: True (previously released)
            # Support all subnet sizes
        })
    
    @staticmethod
    async def allocate_segment(segment_id: str, cluster_name: str) -> bool:
        """Allocate a segment to a cluster (kept for backward compatibility)"""
        storage = get_storage()
        allocation_time = get_current_utc()

        result = await storage.update_one(
            {"_id": segment_id, "cluster_name": None},  # Added condition to prevent race
            {
                "$set": {
                    "cluster_name": cluster_name,
                    "allocated_at": allocation_time,
                    "released": False,
                    "released_at": None
                }
            }
        )
        return result > 0
    
    @staticmethod
    async def release_segment(cluster_name: str, site: str) -> bool:
        """Release a segment allocation
        For shared segments, removes only the specified cluster from the list
        """
        storage = get_storage()

        # First find the segment to check if it's shared
        segment = await storage.find_one({
            "cluster_name": {"$regex": f"(^|,){cluster_name}(,|$)"},
            "site": site,
            "released": False
        })

        if not segment:
            return False

        current_clusters = segment["cluster_name"]

        # If it's an exact match (single cluster), release normally
        if current_clusters == cluster_name:
            result = await storage.update_one(
                {"_id": segment["_id"]},
                {
                    "$set": {
                        "cluster_name": None,
                        "released": True,
                        "released_at": get_current_utc()
                    }
                }
            )
            return result > 0

        # If it's a shared segment, remove only this cluster
        cluster_list = [c.strip() for c in current_clusters.split(",")]
        if cluster_name in cluster_list:
            cluster_list.remove(cluster_name)

            if len(cluster_list) == 0:
                # No clusters left, release the segment
                result = await storage.update_one(
                    {"_id": segment["_id"]},
                    {
                        "$set": {
                            "cluster_name": None,
                            "released": True,
                            "released_at": get_current_utc()
                        }
                    }
                )
            else:
                # Update with remaining clusters
                new_cluster_names = ",".join(cluster_list)
                result = await storage.update_one(
                    {"_id": segment["_id"]},
                    {
                        "$set": {
                            "cluster_name": new_cluster_names
                        }
                    }
                )
            return result > 0

        return False
    
    @staticmethod
    async def get_segments_with_filters(site: Optional[str] = None, allocated: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get segments with optional filters"""
        storage = get_storage()

        query = {}
        if site:
            query["site"] = site
        if allocated is not None:
            if allocated:
                query["cluster_name"] = {"$ne": None}
            else:
                query["cluster_name"] = None

        segments = await storage.find(query)

        # Sort by vlan_id
        segments.sort(key=lambda x: x.get("vlan_id", 0))

        # IDs are already strings in JSON storage
        return segments
    
    @staticmethod
    async def check_vlan_exists(site: str, vlan_id: int) -> bool:
        """Check if VLAN ID already exists for a site"""
        storage = get_storage()

        existing = await storage.find_one({
            "site": site,
            "vlan_id": vlan_id
        })
        return existing is not None

    @staticmethod
    async def check_vlan_exists_excluding_id(site: str, vlan_id: int, exclude_id: str) -> bool:
        """Check if VLAN ID already exists for a site, excluding a specific segment ID"""
        from ..config import settings
        import logging
        logger = logging.getLogger(__name__)

        storage = get_storage()

        query = {
            "site": site,
            "vlan_id": vlan_id,
            "_id": {"$ne": exclude_id}
        }

        logger.debug(f"Checking VLAN existence: site={site}, vlan_id={vlan_id}, exclude_id={exclude_id}")

        existing = await storage.find_one(query)

        if existing:
            logger.debug(f"Found existing VLAN: {existing.get('_id')} (excluding {exclude_id})")
        else:
            logger.debug(f"No conflicting VLAN found")

        return existing is not None

    @staticmethod
    async def create_segment(segment_data: Dict[str, Any]) -> str:
        """Create a new segment"""
        storage = get_storage()

        new_segment = {
            **segment_data,
            "cluster_name": None,
            "allocated_at": None,
            "released": False,
            "released_at": None
        }

        result = await storage.insert_one(new_segment)
        return result

    @staticmethod
    async def get_segment_by_id(segment_id: str) -> Optional[Dict[str, Any]]:
        """Get segment by ID"""
        storage = get_storage()
        return await storage.find_one({"_id": segment_id})

    @staticmethod
    async def update_segment_by_id(segment_id: str, update_data: Dict[str, Any]) -> bool:
        """Update segment by ID"""
        storage = get_storage()
        result = await storage.update_one(
            {"_id": segment_id},
            {"$set": update_data}
        )
        return result > 0

    @staticmethod
    async def delete_segment_by_id(segment_id: str) -> bool:
        """Delete segment by ID"""
        storage = get_storage()
        result = await storage.delete_one({"_id": segment_id})
        return result > 0
    
    @staticmethod
    async def get_site_statistics(site: str) -> Dict[str, Any]:
        """Get statistics for a specific site"""
        storage = get_storage()

        total_segments = await storage.count_documents({"site": site})
        allocated = await storage.count_documents({
            "site": site,
            "cluster_name": {"$ne": None},
            "released": False
        })

        return {
            "site": site,
            "total_segments": total_segments,
            "allocated": allocated,
            "available": total_segments - allocated,
            "utilization": round((allocated / total_segments * 100) if total_segments > 0 else 0, 1)
        }

    @staticmethod
    async def search_segments(
        search_query: str,
        site: Optional[str] = None,
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Search segments by cluster name, EPG name, or VLAN ID"""
        storage = get_storage()

        # Build base query with optional filters
        query = {}
        if site:
            query["site"] = site
        if allocated is not None:
            if allocated:
                query["cluster_name"] = {"$ne": None}
            else:
                query["cluster_name"] = None

        # Add search conditions - search in multiple fields
        search_conditions = []

        # Try to parse as VLAN ID (integer)
        try:
            vlan_id = int(search_query)
            search_conditions.append({"vlan_id": vlan_id})
        except ValueError:
            pass  # Not a valid integer, skip VLAN ID search

        # Search in text fields (case-insensitive)
        text_search = {"$regex": search_query, "$options": "i"}
        search_conditions.extend([
            {"cluster_name": text_search},
            {"epg_name": text_search},
            {"description": text_search},
            {"segment": text_search}
        ])

        # Combine search conditions with OR
        if search_conditions:
            query["$or"] = search_conditions

        segments = await storage.find(query)

        # Sort by vlan_id
        segments.sort(key=lambda x: x.get("vlan_id", 0))

        # IDs are already strings in JSON storage
        return segments
    @staticmethod
    async def get_vrfs() -> List[str]:
        """Get list of available VRFs from NetBox"""
        storage = get_storage()
        return await storage.get_vrfs()
