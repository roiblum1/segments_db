import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId
from pymongo import ReturnDocument

from ..database.mongodb import get_segments_collection
from ..config.settings import SITES

logger = logging.getLogger(__name__)

class DatabaseUtils:
    """Utility class for database operations"""
    
    @staticmethod
    async def find_existing_allocation(cluster_name: str, site: str) -> Optional[Dict[str, Any]]:
        """Find existing allocation for a cluster at a site"""
        segments_collection = get_segments_collection()
        return await segments_collection.find_one({
            "cluster_name": cluster_name,
            "site": site,
            "released": False
        })
    
    @staticmethod
    async def find_and_allocate_segment(site: str, cluster_name: str) -> Optional[Dict[str, Any]]:
        """Atomically find and allocate an available segment for a site"""
        segments_collection = get_segments_collection()
        allocation_time = datetime.utcnow()
        
        # Use findOneAndUpdate for atomic operation - prevents race conditions
        # Find segments that are either never allocated (released: False, cluster_name: None) 
        # OR have been released (released: True, cluster_name: None)
        # Sort by vlan_id to always allocate the smallest available VLAN ID first
        result = await segments_collection.find_one_and_update(
            {
                "site": site,
                "cluster_name": None
                # Remove released: False condition to allow reuse of released segments
            },
            {
                "$set": {
                    "cluster_name": cluster_name,
                    "allocated_at": allocation_time,
                    "released": False,
                    "released_at": None
                }
            },
            sort=[("vlan_id", 1)],  # Sort by vlan_id ascending to get smallest first
            return_document=ReturnDocument.AFTER
        )
        return result
    
    @staticmethod
    async def find_available_segment(site: str) -> Optional[Dict[str, Any]]:
        """Find an available segment for a site (kept for backward compatibility)"""
        segments_collection = get_segments_collection()
        return await segments_collection.find_one({
            "site": site,
            "cluster_name": None
            # Allow both released: False (never allocated) and released: True (previously released)
        })
    
    @staticmethod
    async def allocate_segment(segment_id: ObjectId, cluster_name: str) -> bool:
        """Allocate a segment to a cluster (kept for backward compatibility)"""
        segments_collection = get_segments_collection()
        allocation_time = datetime.utcnow()
        
        result = await segments_collection.update_one(
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
        return result.modified_count > 0
    
    @staticmethod
    async def release_segment(cluster_name: str, site: str) -> bool:
        """Release a segment allocation"""
        segments_collection = get_segments_collection()
        
        result = await segments_collection.update_one(
            {
                "cluster_name": cluster_name,
                "site": site,
                "released": False
            },
            {
                "$set": {
                    "cluster_name": None,
                    "released": True,
                    "released_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    @staticmethod
    async def get_segments_with_filters(site: Optional[str] = None, allocated: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get segments with optional filters"""
        segments_collection = get_segments_collection()
        
        query = {}
        if site:
            query["site"] = site
        if allocated is not None:
            if allocated:
                query["cluster_name"] = {"$ne": None}
            else:
                query["cluster_name"] = None
        
        segments = await segments_collection.find(query).sort("vlan_id", 1).to_list(None)
        
        # Convert ObjectId to string
        for segment in segments:
            segment["_id"] = str(segment["_id"])
        
        return segments
    
    @staticmethod
    async def check_vlan_exists(site: str, vlan_id: int) -> bool:
        """Check if VLAN ID already exists for a site"""
        segments_collection = get_segments_collection()
        
        existing = await segments_collection.find_one({
            "site": site,
            "vlan_id": vlan_id
        })
        return existing is not None
    
    @staticmethod
    async def create_segment(segment_data: Dict[str, Any]) -> str:
        """Create a new segment"""
        segments_collection = get_segments_collection()
        
        new_segment = {
            **segment_data,
            "cluster_name": None,
            "allocated_at": None,
            "released": False,
            "released_at": None
        }
        
        result = await segments_collection.insert_one(new_segment)
        return str(result.inserted_id)
    
    @staticmethod
    async def get_segment_by_id(segment_id: str) -> Optional[Dict[str, Any]]:
        """Get segment by ID"""
        if not ObjectId.is_valid(segment_id):
            return None
            
        segments_collection = get_segments_collection()
        return await segments_collection.find_one({"_id": ObjectId(segment_id)})
    
    @staticmethod
    async def delete_segment_by_id(segment_id: str) -> bool:
        """Delete segment by ID"""
        if not ObjectId.is_valid(segment_id):
            return False
            
        segments_collection = get_segments_collection()
        result = await segments_collection.delete_one({"_id": ObjectId(segment_id)})
        return result.deleted_count > 0
    
    @staticmethod
    async def get_site_statistics(site: str) -> Dict[str, Any]:
        """Get statistics for a specific site"""
        segments_collection = get_segments_collection()
        
        total_segments = await segments_collection.count_documents({"site": site})
        allocated = await segments_collection.count_documents({
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