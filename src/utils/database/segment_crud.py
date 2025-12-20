"""CRUD operations for VLAN segments.

Handles create, read, update, delete operations for segments.
"""

import logging
from typing import Optional, Dict, Any

from ...database.netbox_storage import get_storage

logger = logging.getLogger(__name__)


class SegmentCRUD:
    """Basic CRUD operations for segments"""

    @staticmethod
    async def create_segment(segment_data: Dict[str, Any]) -> str:
        """Create a new segment

        Returns:
            Segment ID as string
        """
        storage = get_storage()

        new_segment = {
            **segment_data,
            "cluster_name": None,
            "allocated_at": None,
            "released": False,
            "released_at": None
        }

        result = await storage.insert_one(new_segment)
        # insert_one returns a dict with "_id" field, extract it
        if isinstance(result, dict) and "_id" in result:
            return str(result["_id"])
        elif isinstance(result, str):
            return result
        else:
            logger.warning(f"Unexpected return type from insert_one: {type(result)}, value: {result}")
            # Fallback: try to get ID from result
            return str(result.get("_id", result)) if isinstance(result, dict) else str(result)

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
        return result  # Result is already bool, no need for > 0 comparison

    @staticmethod
    async def delete_segment_by_id(segment_id: str) -> bool:
        """Delete segment by ID"""
        storage = get_storage()
        result = await storage.delete_one({"_id": segment_id})
        return result  # Result is already bool, no need for > 0 comparison
