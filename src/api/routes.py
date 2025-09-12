from typing import Optional, List
from fastapi import APIRouter

from ..models.schemas import (
    VLANAllocationRequest, VLANAllocationResponse, 
    VLANRelease, SegmentCreate
)
from ..services.vlan_service import VLANService
from ..services.segment_service import SegmentService
from ..services.stats_service import StatsService
from ..services.logs_service import LogsService

router = APIRouter()

# VLAN Management Routes
@router.post("/allocate-vlan", response_model=VLANAllocationResponse)
async def allocate_vlan(request: VLANAllocationRequest):
    """Allocate a VLAN segment for a cluster"""
    return await VLANService.allocate_vlan(request)

@router.post("/release-vlan")
async def release_vlan(request: VLANRelease):
    """Release a VLAN segment allocation"""
    return await VLANService.release_vlan(request.cluster_name, request.site)

# Segment Management Routes
@router.get("/segments")
async def get_segments(site: Optional[str] = None, allocated: Optional[bool] = None):
    """Get segments with optional filters"""
    return await SegmentService.get_segments(site, allocated)

@router.post("/segments")
async def create_segment(segment: SegmentCreate):
    """Create a new segment"""
    return await SegmentService.create_segment(segment)

@router.delete("/segments/{segment_id}")
async def delete_segment(segment_id: str):
    """Delete a segment"""
    return await SegmentService.delete_segment(segment_id)

@router.post("/segments/bulk")
async def create_segments_bulk(segments: List[SegmentCreate]):
    """Create multiple segments at once"""
    return await SegmentService.create_segments_bulk(segments)

# Statistics and Configuration Routes
@router.get("/sites")
async def get_sites():
    """Get configured sites"""
    return await StatsService.get_sites()

@router.get("/stats")
async def get_stats():
    """Get statistics per site"""
    return await StatsService.get_stats()

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return await StatsService.health_check()

# Logs Management Routes
@router.get("/logs")
async def get_logs(lines: int = 100):
    """Get the contents of the vlan_manager.log file
    
    Args:
        lines: Number of lines to retrieve from the end of the log file (default: 100)
    """
    return await LogsService.get_logs(lines)

@router.get("/logs/info")
async def get_log_info():
    """Get information about the log file (size, location, etc.)"""
    return await LogsService.get_log_info()