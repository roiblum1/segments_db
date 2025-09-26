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
        """Find existing allocation for a cluster at a site
        Supports both single clusters and shared segments (comma-separated)
        """
        segments_collection = get_segments_collection()
        
        # Check for exact match first (single cluster or comma-separated list including this cluster)
        exact_match = await segments_collection.find_one({
            "cluster_name": cluster_name,
            "site": site,
            "released": False
        })
        if exact_match:
            return exact_match
        
        # Check for shared segments where this cluster is part of a comma-separated list
        shared_match = await segments_collection.find_one({
            "cluster_name": {"$regex": f"(^|,){cluster_name}(,|$)"},
            "site": site,
            "released": False
        })
        return shared_match
    
    @staticmethod
    async def find_and_allocate_segment(site: str, cluster_name: str) -> Optional[Dict[str, Any]]:
        """Atomically find and allocate an available segment for a site
        Supports all subnet sizes (/24, /21, /16, etc.) for cluster allocation
        """
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
                # Remove subnet size restriction - allow all sizes
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
        """Find an available segment for a site (kept for backward compatibility)
        Returns any available segment regardless of subnet size
        """
        segments_collection = get_segments_collection()
        return await segments_collection.find_one({
            "site": site,
            "cluster_name": None
            # Allow both released: False (never allocated) and released: True (previously released)
            # Support all subnet sizes
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
        """Release a segment allocation
        For shared segments, removes only the specified cluster from the list
        """
        segments_collection = get_segments_collection()
        
        # First find the segment to check if it's shared
        segment = await segments_collection.find_one({
            "cluster_name": {"$regex": f"(^|,){cluster_name}(,|$)"},
            "site": site,
            "released": False
        })
        
        if not segment:
            return False
        
        current_clusters = segment["cluster_name"]
        
        # If it's an exact match (single cluster), release normally
        if current_clusters == cluster_name:
            result = await segments_collection.update_one(
                {"_id": segment["_id"]},
                {
                    "$set": {
                        "cluster_name": None,
                        "released": True,
                        "released_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        
        # If it's a shared segment, remove only this cluster
        cluster_list = [c.strip() for c in current_clusters.split(",")]
        if cluster_name in cluster_list:
            cluster_list.remove(cluster_name)
            
            if len(cluster_list) == 0:
                # No clusters left, release the segment
                result = await segments_collection.update_one(
                    {"_id": segment["_id"]},
                    {
                        "$set": {
                            "cluster_name": None,
                            "released": True,
                            "released_at": datetime.utcnow()
                        }
                    }
                )
            else:
                # Update with remaining clusters
                new_cluster_names = ",".join(cluster_list)
                result = await segments_collection.update_one(
                    {"_id": segment["_id"]},
                    {
                        "$set": {
                            "cluster_name": new_cluster_names
                        }
                    }
                )
            return result.modified_count > 0
        
        return False
    
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
    async def check_vlan_exists_excluding_id(site: str, vlan_id: int, exclude_id: str) -> bool:
        """Check if VLAN ID already exists for a site, excluding a specific segment ID"""
        from bson import ObjectId
        segments_collection = get_segments_collection()
        
        existing = await segments_collection.find_one({
            "site": site,
            "vlan_id": vlan_id,
            "_id": {"$ne": ObjectId(exclude_id)}
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
    async def update_segment_by_id(segment_id: str, update_data: Dict[str, Any]) -> bool:
        """Update segment by ID"""
        if not ObjectId.is_valid(segment_id):
            return False
            
        segments_collection = get_segments_collection()
        result = await segments_collection.update_one(
            {"_id": ObjectId(segment_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
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
    
    @staticmethod
    async def search_segments(
        search_query: str, 
        site: Optional[str] = None, 
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Search segments by cluster name, EPG name, or VLAN ID"""
        segments_collection = get_segments_collection()
        
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
        
        segments = await segments_collection.find(query).sort("vlan_id", 1).to_list(None)
        
        # Convert ObjectId to string
        for segment in segments:
            segment["_id"] = str(segment["_id"])
        
        return segments