"""Allocation utilities for VLAN segment management.

Handles all allocation-related operations including finding allocations,
atomic allocation, releasing segments, and supporting shared segments.
"""

import logging
import time
from typing import Optional, Dict, Any

from ...database.netbox_storage import get_storage
from ..time_utils import get_current_utc

logger = logging.getLogger(__name__)


class AllocationUtils:
    """Utilities for segment allocation operations"""

    @staticmethod
    async def find_existing_allocation(cluster_name: str, site: str, vrf: str = None) -> Optional[Dict[str, Any]]:
        """Find existing allocation for a cluster at a site and VRF
        Supports both single clusters and shared segments (comma-separated)
        
        Args:
            cluster_name: Name of the cluster
            site: Site name
            vrf: VRF/Network name (optional, but recommended for correct matching)

        Uses optimized NetBox API filtering to reduce data transfer
        """
        storage = get_storage()

        # Build query filter - VRF is important to ensure correct network matching
        query_filter = {
            "cluster_name": cluster_name,
            "site": site,
            "released": False
        }
        
        # Add VRF filter if provided
        if vrf:
            query_filter["vrf"] = vrf

        # Use optimized find for exact match first
        exact_match = await storage.find_one_optimized(query_filter)
        if exact_match:
            return exact_match

        # For regex search (shared segments), we still need find_one
        # but this is rare, so less impact
        shared_query_filter = {
            "cluster_name": {"$regex": f"(^|,){cluster_name}(,|$)"},
            "site": site,
            "released": False
        }
        
        # Add VRF filter if provided
        if vrf:
            shared_query_filter["vrf"] = vrf
            
        shared_match = await storage.find_one(shared_query_filter)
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
    async def release_segment(cluster_name: str, site: str, vrf: str = None) -> bool:
        """Release a segment allocation
        For shared segments, removes only the specified cluster from the list
        
        Args:
            cluster_name: Name of the cluster to release
            site: Site name
            vrf: VRF/Network name (optional, but recommended for correct matching)
        """
        storage = get_storage()

        # Build query filter - VRF is important to ensure correct network matching
        query_filter = {
            "cluster_name": {"$regex": f"(^|,){cluster_name}(,|$)"},
            "site": site,
            "released": False
        }
        
        # Add VRF filter if provided
        if vrf:
            query_filter["vrf"] = vrf

        # First find the segment to check if it's shared
        segment = await storage.find_one(query_filter)

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
