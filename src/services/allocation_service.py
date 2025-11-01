import logging
from typing import Dict, Any
from datetime import datetime
from fastapi import HTTPException

from ..models.schemas import VLANAllocationRequest, VLANAllocationResponse
from ..utils.database_utils import DatabaseUtils
from ..utils.validators import Validators

logger = logging.getLogger(__name__)

class AllocationService:
    """Service class for segment allocation operations"""
    
    @staticmethod
    async def allocate_vlan(request: VLANAllocationRequest) -> VLANAllocationResponse:
        """Allocate a VLAN segment for a cluster"""
        logger.info(f"Allocation request: cluster={request.cluster_name}, site={request.site}")

        # Validate inputs
        Validators.validate_site(request.site)
        Validators.validate_cluster_name(request.cluster_name)
        
        try:
            # Check if cluster already has an allocation at this site
            existing = await DatabaseUtils.find_existing_allocation(
                request.cluster_name, request.site
            )
            
            if existing:
                logger.info(f"Returning existing allocation: VLAN {existing['vlan_id']} for {request.cluster_name}")
                return VLANAllocationResponse(
                    vlan_id=existing["vlan_id"],
                    cluster_name=existing["cluster_name"],
                    site=existing["site"],
                    segment=existing["segment"],
                    epg_name=existing["epg_name"],
                    allocated_at=existing["allocated_at"]
                )
            
            # Atomically find and allocate an available segment for this site
            allocated_segment = await DatabaseUtils.find_and_allocate_segment(
                request.site, request.cluster_name
            )
            
            if not allocated_segment:
                logger.error(f"No available segments for site: {request.site}")
                raise HTTPException(
                    status_code=503, 
                    detail=f"No available segments for site: {request.site}"
                )
            
            logger.info(f"Allocated VLAN {allocated_segment['vlan_id']} (EPG: {allocated_segment['epg_name']}) to {request.cluster_name}")
            
            return VLANAllocationResponse(
                vlan_id=allocated_segment["vlan_id"],
                cluster_name=request.cluster_name,
                site=request.site,
                segment=allocated_segment["segment"],
                epg_name=allocated_segment["epg_name"],
                allocated_at=allocated_segment["allocated_at"]
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error allocating VLAN: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def release_vlan(cluster_name: str, site: str) -> Dict[str, str]:
        """Release a VLAN segment allocation"""
        logger.info(f"Release request: cluster={cluster_name}, site={site}")
        
        try:
            success = await DatabaseUtils.release_segment(cluster_name, site)
            
            if not success:
                logger.warning(f"Allocation not found for release: {cluster_name} at {site}")
                raise HTTPException(status_code=404, detail="Allocation not found")
            
            logger.info(f"Released VLAN for {cluster_name} at {site}")
            return {"message": "VLAN released successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error releasing VLAN: {e}")
            raise HTTPException(status_code=500, detail=str(e))