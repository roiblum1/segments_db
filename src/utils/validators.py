import logging
from typing import List, Dict, Any
from fastapi import HTTPException
from bson import ObjectId

from ..config.settings import SITES

logger = logging.getLogger(__name__)

class Validators:
    """Validation utilities"""
    
    @staticmethod
    def validate_site(site: str) -> None:
        """Validate if site is in configured sites"""
        if site not in SITES:
            logger.warning(f"Invalid site requested: {site}")
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid site. Must be one of: {SITES}"
            )
    
    @staticmethod
    def validate_object_id(object_id: str) -> None:
        """Validate ObjectId format"""
        if not ObjectId.is_valid(object_id):
            raise HTTPException(
                status_code=400, 
                detail="Invalid ID format"
            )
    
    @staticmethod
    def validate_segment_not_allocated(segment: Dict[str, Any]) -> None:
        """Validate that segment is not currently allocated"""
        if segment.get("cluster_name") and not segment.get("released", False):
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete allocated segment"
            )
    
    @staticmethod
    def validate_bulk_segments(segments: List[Dict[str, Any]]) -> List[str]:
        """Validate bulk segments and return list of errors"""
        errors = []
        
        for segment in segments:
            if segment.get("site") not in SITES:
                errors.append(f"Invalid site: {segment.get('site')}")
        
        return errors