"""Query and search operations for VLAN segments.

Handles filtering, searching, and checking VLAN existence.
"""

import logging
from typing import Optional, List, Dict, Any

from ...database.netbox_storage import get_storage

logger = logging.getLogger(__name__)


class SegmentQueries:
    """Query and search operations for segments"""

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
