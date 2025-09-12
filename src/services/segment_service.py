import logging
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from ..models.schemas import SegmentCreate
from ..utils.database_utils import DatabaseUtils
from ..utils.validators import Validators
from ..config.settings import SITES

logger = logging.getLogger(__name__)

class SegmentService:
    """Service class for segment management operations"""
    
    @staticmethod
    async def get_segments(site: Optional[str] = None, allocated: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get segments with optional filters"""
        try:
            segments = await DatabaseUtils.get_segments_with_filters(site, allocated)
            logger.debug(f"Retrieved {len(segments)} segments")
            return segments
        except Exception as e:
            logger.error(f"Error retrieving segments: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def create_segment(segment: SegmentCreate) -> Dict[str, str]:
        """Create a new segment"""
        logger.info(f"Creating segment: site={segment.site}, vlan_id={segment.vlan_id}, epg={segment.epg_name}")
        
        try:
            # Validate site
            Validators.validate_site(segment.site)
            
            # Check if VLAN ID already exists for this site
            if await DatabaseUtils.check_vlan_exists(segment.site, segment.vlan_id):
                logger.warning(f"VLAN {segment.vlan_id} already exists for site {segment.site}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"VLAN {segment.vlan_id} already exists for site {segment.site}"
                )
            
            # Create the segment
            segment_data = {
                "site": segment.site,
                "vlan_id": segment.vlan_id,
                "epg_name": segment.epg_name,
                "segment": segment.segment,
                "description": segment.description
            }
            
            segment_id = await DatabaseUtils.create_segment(segment_data)
            logger.info(f"Created segment with ID: {segment_id}")
            
            return {"message": "Segment created", "id": segment_id}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def delete_segment(segment_id: str) -> Dict[str, str]:
        """Delete a segment"""
        logger.info(f"Deleting segment: {segment_id}")
        
        try:
            # Validate ObjectId format
            Validators.validate_object_id(segment_id)
            
            # Check if segment exists and is not allocated
            segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")
            
            # Validate segment can be deleted
            Validators.validate_segment_not_allocated(segment)
            
            # Delete the segment
            success = await DatabaseUtils.delete_segment_by_id(segment_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete segment")
            
            logger.info(f"Deleted segment {segment_id}")
            return {"message": "Segment deleted"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def create_segments_bulk(segments: List[SegmentCreate]) -> Dict[str, Any]:
        """Create multiple segments at once"""
        logger.info(f"Bulk creating {len(segments)} segments")
        
        try:
            created = 0
            errors = []
            
            for segment in segments:
                try:
                    # Validate site
                    Validators.validate_site(segment.site)
                    
                    # Check if VLAN ID already exists for this site
                    if await DatabaseUtils.check_vlan_exists(segment.site, segment.vlan_id):
                        errors.append(f"VLAN {segment.vlan_id} already exists for site {segment.site}")
                        continue
                    
                    # Create the segment
                    segment_data = {
                        "site": segment.site,
                        "vlan_id": segment.vlan_id,
                        "epg_name": segment.epg_name,
                        "segment": segment.segment,
                        "description": segment.description
                    }
                    
                    await DatabaseUtils.create_segment(segment_data)
                    created += 1
                    
                except HTTPException as e:
                    errors.append(f"Site {segment.site}, VLAN {segment.vlan_id}: {e.detail}")
                except Exception as e:
                    errors.append(f"Site {segment.site}, VLAN {segment.vlan_id}: {str(e)}")
            
            return {
                "message": f"Created {created} segments",
                "created": created,
                "errors": errors if errors else None
            }
            
        except Exception as e:
            logger.error(f"Error in bulk creation: {e}")
            raise HTTPException(status_code=500, detail=str(e))