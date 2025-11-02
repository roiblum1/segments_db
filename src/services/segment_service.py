import logging
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from ..models.schemas import Segment
from ..utils.database_utils import DatabaseUtils
from ..utils.validators import Validators

logger = logging.getLogger(__name__)

class SegmentService:
    """Service class for segment management operations"""
    
    @staticmethod
    async def _validate_segment_data(segment: Segment, exclude_id: str = None) -> None:
        """Common validation for segment data"""
        # Basic field validation
        Validators.validate_site(segment.site)
        Validators.validate_epg_name(segment.epg_name)
        Validators.validate_vlan_id(segment.vlan_id)

        # Network validation
        Validators.validate_segment_format(segment.segment, segment.site)
        Validators.validate_subnet_mask(segment.segment)
        Validators.validate_no_reserved_ips(segment.segment)
        Validators.validate_network_broadcast_gateway(segment.segment)

        # Description validation (XSS protection)
        if segment.description:
            Validators.validate_description(segment.description)
            Validators.validate_no_script_injection(segment.description, "description")

        # EPG name XSS protection
        Validators.validate_no_script_injection(segment.epg_name, "epg_name")

        # IP overlap validation - get all existing segments
        existing_segments = await DatabaseUtils.get_segments_with_filters()
        if exclude_id:
            # Exclude the segment being updated
            existing_segments = [s for s in existing_segments if str(s.get("_id")) != str(exclude_id)]

        Validators.validate_ip_overlap(segment.segment, existing_segments)

        # EPG name uniqueness validation
        Validators.validate_vlan_name_uniqueness(
            site=segment.site,
            epg_name=segment.epg_name,
            vlan_id=segment.vlan_id,
            existing_segments=existing_segments,
            exclude_id=exclude_id
        )
    
    @staticmethod
    def _segment_to_dict(segment: Segment) -> Dict[str, Any]:
        """Convert segment object to dictionary"""
        return {
            "site": segment.site,
            "vlan_id": segment.vlan_id,
            "epg_name": segment.epg_name,
            "segment": segment.segment,
            "vrf": segment.vrf,
            "dhcp": segment.dhcp,
            "description": segment.description
        }
    
    @staticmethod
    async def get_segments(site: Optional[str] = None, allocated: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get segments with optional filters"""
        logger.info(f"Getting segments: site={site}, allocated={allocated}")
        try:
            segments = await DatabaseUtils.get_segments_with_filters(site, allocated)
            logger.info(f"Retrieved {len(segments)} segments")
            return segments
        except Exception as e:
            logger.error(f"Error retrieving segments: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def search_segments(
        search_query: str, 
        site: Optional[str] = None, 
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Search segments by cluster name, EPG name, VLAN ID, description, or segment"""
        logger.info(f"Searching segments: query='{search_query}', site={site}, allocated={allocated}")
        
        try:
            segments = await DatabaseUtils.search_segments(search_query, site, allocated)
            logger.debug(f"Found {len(segments)} matching segments")
            return segments
        except Exception as e:
            logger.error(f"Error searching segments: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def create_segment(segment: Segment) -> Dict[str, str]:
        """Create a new segment"""
        logger.info(f"Creating segment: site={segment.site}, vlan_id={segment.vlan_id}, epg={segment.epg_name}")
        logger.debug(f"DEBUG: Full segment data - {segment}")
        
        try:
            # Validate segment data
            logger.debug(f"DEBUG: Starting validation for segment {segment.vlan_id}")
            await SegmentService._validate_segment_data(segment)
            logger.debug(f"DEBUG: Validation completed for segment {segment.vlan_id}")
            
            # Check if VLAN ID already exists for this site
            if await DatabaseUtils.check_vlan_exists(segment.site, segment.vlan_id):
                logger.warning(f"VLAN {segment.vlan_id} already exists for site {segment.site}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"VLAN {segment.vlan_id} already exists for site {segment.site}"
                )
            
            # Create the segment
            segment_data = SegmentService._segment_to_dict(segment)
            
            segment_id = await DatabaseUtils.create_segment(segment_data)
            logger.info(f"Created segment with ID: {segment_id}")
            
            return {"message": "Segment created", "id": segment_id}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def get_segment_by_id(segment_id: str) -> Dict[str, Any]:
        """Get a single segment by ID"""
        logger.info(f"Getting segment: {segment_id}")
        
        try:
            # Validate ObjectId format
            Validators.validate_object_id(segment_id)
            
            # Get the segment
            segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")
            
            # Convert ObjectId to string
            segment["_id"] = str(segment["_id"])
            
            logger.info(f"Retrieved segment {segment_id}: site={segment.get('site')}, vlan_id={segment.get('vlan_id')}")
            return segment
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def update_segment(segment_id: str, updated_segment: Segment) -> Dict[str, str]:
        """Update a segment"""
        logger.info(f"Updating segment: {segment_id}")
        
        try:
            # Validate ObjectId format
            Validators.validate_object_id(segment_id)
            
            # Validate segment data (exclude self from overlap check)
            await SegmentService._validate_segment_data(updated_segment, exclude_id=segment_id)
            
            # Check if segment exists
            existing_segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not existing_segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")
            
            # Check if VLAN ID change would conflict (only if changing VLAN ID or site)
            if (existing_segment["vlan_id"] != updated_segment.vlan_id or 
                existing_segment["site"] != updated_segment.site):
                if await DatabaseUtils.check_vlan_exists_excluding_id(updated_segment.site, updated_segment.vlan_id, segment_id):
                    logger.warning(f"VLAN {updated_segment.vlan_id} already exists for site {updated_segment.site}")
                    raise HTTPException(
                        status_code=400, 
                        detail=f"VLAN {updated_segment.vlan_id} already exists for site {updated_segment.site}"
                    )
            
            # Update the segment
            update_data = SegmentService._segment_to_dict(updated_segment)
            success = await DatabaseUtils.update_segment_by_id(segment_id, update_data)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update segment")
            
            logger.info(f"Updated segment {segment_id}")
            return {"message": "Segment updated successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def update_segment_clusters(segment_id: str, cluster_names: str) -> Dict[str, str]:
        """Update cluster assignment for a segment (for shared segments)"""
        from datetime import datetime, timezone
        logger.info(f"Updating cluster assignment for segment: {segment_id}")
        
        try:
            # Validate ObjectId format
            Validators.validate_object_id(segment_id)
            
            # Check if segment exists
            existing_segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not existing_segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")
            
            # Clean up cluster names
            clean_cluster_names = cluster_names.strip() if cluster_names else None
            
            # Update the segment cluster assignment
            update_data = {}
            if clean_cluster_names:
                # Validate cluster names format (comma-separated, no special chars)
                cluster_list = [name.strip() for name in clean_cluster_names.split(",")]
                validated_clusters = []
                for cluster in cluster_list:
                    if cluster and cluster.replace("-", "").replace("_", "").isalnum():
                        validated_clusters.append(cluster)
                
                if validated_clusters:
                    update_data["cluster_name"] = ",".join(validated_clusters)
                    update_data["allocated_at"] = datetime.now(timezone.utc)
                    update_data["released"] = False
                    update_data["released_at"] = None
                else:
                    # No valid clusters, release the segment
                    update_data["cluster_name"] = None
                    update_data["released"] = True
                    update_data["released_at"] = datetime.now(timezone.utc)
            else:
                # Empty cluster names, release the segment
                update_data["cluster_name"] = None
                update_data["released"] = True
                update_data["released_at"] = datetime.now(timezone.utc)
            
            success = await DatabaseUtils.update_segment_by_id(segment_id, update_data)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update segment clusters")
            
            logger.info(f"Updated cluster assignment for segment {segment_id}")
            return {"message": "Segment cluster assignment updated successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating segment clusters: {e}")
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
    async def create_segments_bulk(segments: List[Segment]) -> Dict[str, Any]:
        """Create multiple segments at once"""
        logger.info(f"Bulk creating {len(segments)} segments")
        
        try:
            created = 0
            errors = []
            
            for segment in segments:
                try:
                    # Validate segment data
                    await SegmentService._validate_segment_data(segment)
                    
                    # Check if VLAN ID already exists for this site
                    if await DatabaseUtils.check_vlan_exists(segment.site, segment.vlan_id):
                        errors.append(f"VLAN {segment.vlan_id} already exists for site {segment.site}")
                        continue
                    
                    # Create the segment
                    segment_data = SegmentService._segment_to_dict(segment)
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

    @staticmethod
    async def get_vrfs() -> Dict[str, Any]:
        """Get list of available VRFs from NetBox"""
        logger.info("Fetching VRFs from NetBox")
        try:
            vrfs = await DatabaseUtils.get_vrfs()
            logger.info(f"Retrieved {len(vrfs)} VRFs")
            return {"vrfs": vrfs}
        except Exception as e:
            logger.error(f"Error retrieving VRFs: {e}")
            raise HTTPException(status_code=500, detail=str(e))