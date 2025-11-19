from typing import Optional, List
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..models.schemas import (
    VLANAllocationRequest, VLANAllocationResponse, 
    VLANRelease, Segment
)
from ..services.allocation_service import AllocationService
from ..services.segment_service import SegmentService
from ..services.stats_service import StatsService
from ..services.logs_service import LogsService
from ..services.export_service import ExportService

router = APIRouter()

# VLAN Management Routes
@router.post("/allocate-vlan", response_model=VLANAllocationResponse)
async def allocate_vlan(request: VLANAllocationRequest):
    """Allocate a VLAN segment for a cluster"""
    return await AllocationService.allocate_vlan(request)

@router.post("/release-vlan")
async def release_vlan(request: VLANRelease):
    """Release a VLAN segment allocation"""
    return await AllocationService.release_vlan(request.cluster_name, request.site)

# Segment Management Routes
@router.get("/segments")
async def get_segments(site: Optional[str] = None, allocated: Optional[bool] = None):
    """Get segments with optional filters"""
    return await SegmentService.get_segments(site, allocated)

@router.get("/segments/search")
async def search_segments(
    q: str, 
    site: Optional[str] = None, 
    allocated: Optional[bool] = None
):
    """Search segments by cluster name, EPG name, VLAN ID, description, or segment"""
    return await SegmentService.search_segments(q, site, allocated)

@router.post("/segments")
async def create_segment(segment: Segment):
    """Create a new segment"""
    return await SegmentService.create_segment(segment)

@router.get("/segments/{segment_id}")
async def get_segment(segment_id: str):
    """Get a single segment by ID"""
    return await SegmentService.get_segment_by_id(segment_id)

@router.put("/segments/{segment_id}")
async def update_segment(segment_id: str, segment: Segment):
    """Update a segment"""
    return await SegmentService.update_segment(segment_id, segment)

@router.put("/segments/{segment_id}/clusters")
async def update_segment_clusters(segment_id: str, request: dict):
    """Update cluster assignment for a segment (for shared segments)"""
    cluster_names = request.get("cluster_names", "")
    return await SegmentService.update_segment_clusters(segment_id, cluster_names)

@router.delete("/segments/{segment_id}")
async def delete_segment(segment_id: str):
    """Delete a segment"""
    return await SegmentService.delete_segment(segment_id)

@router.post("/segments/bulk")
async def create_segments_bulk(segments: List[Segment]):
    """Create multiple segments at once"""
    logger = logging.getLogger(__name__)
    
    if not segments or len(segments) == 0:
        logger.warning("Bulk create called with empty segments list")
        raise HTTPException(status_code=400, detail="No segments provided. Please check your CSV data format.")
    
    logger.info(f"Received bulk create request with {len(segments)} segments")
    return await SegmentService.create_segments_bulk(segments)

# Statistics and Configuration Routes
@router.get("/sites")
async def get_sites():
    """Get configured sites"""
    return await StatsService.get_sites()

@router.get("/vrfs")
async def get_vrfs():
    """Get list of available VRFs from NetBox"""
    return await SegmentService.get_vrfs()

@router.get("/stats")
async def get_stats():
    """Get statistics per site"""
    return await StatsService.get_stats()

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return await StatsService.health_check()

# Export Routes
@router.get("/export/segments/csv")
async def export_segments_csv(
    site: Optional[str] = None, 
    allocated: Optional[bool] = None
):
    """Export segments data as CSV"""
    return await ExportService.export_segments_csv(site=site, allocated=allocated)

@router.get("/export/segments/excel")
async def export_segments_excel(
    site: Optional[str] = None, 
    allocated: Optional[bool] = None
):
    """Export segments data as Excel"""
    return await ExportService.export_segments_excel(site=site, allocated=allocated)

@router.get("/export/stats/csv")
async def export_stats_csv():
    """Export site statistics as CSV"""
    return await ExportService.export_stats_csv()

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