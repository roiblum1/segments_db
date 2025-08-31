"""
API endpoints for network segment management.
"""
from typing import List, Optional
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.segment import Segment
from app.schemas.segment import (
    SegmentCreate, SegmentUpdate, SegmentResponse, 
    SegmentAllocation, SegmentStats, ZoneStats
)

logger = get_logger("api.segments")
router = APIRouter(prefix="/api", tags=["segments"])


def get_db_session():
    """Dependency to get database session."""
    with get_db() as db:
        yield db


@router.get("/segments", response_model=List[SegmentResponse])
async def get_all_segments(
    zone: Optional[str] = Query(None, description="Filter by zone/office"),
    in_use: Optional[bool] = Query(None, description="Filter by usage status"),
    cluster: Optional[str] = Query(None, description="Filter by cluster name"),
    db: Session = Depends(get_db_session)
):
    """Get all segments with optional filtering by zone, usage, and cluster."""
    logger.info(f"Fetching segments - zone: {zone}, in_use: {in_use}, cluster: {cluster}")
    
    query = db.query(Segment)
    
    if zone:
        query = query.filter(Segment.zone == zone)
    
    if in_use is not None:
        query = query.filter(Segment.in_use == in_use)
    
    if cluster:
        query = query.filter(Segment.cluster_using == cluster.lower())
    
    segments = query.order_by(Segment.zone, Segment.id).all()
    logger.info(f"Found {len(segments)} segments")
    return segments


@router.get("/segments/available", response_model=SegmentResponse)
async def get_available_segment(
    zone: Optional[str] = Query(None, description="Filter by zone/office"),
    db: Session = Depends(get_db_session)
):
    """Get the first available (not in use) segment from the pool, optionally filtered by zone."""
    logger.info(f"Requesting available segment from pool - zone: {zone}")
    
    query = db.query(Segment).filter(
        and_(Segment.in_use == False, Segment.cluster_using.is_(None))
    )
    
    if zone:
        query = query.filter(Segment.zone == zone)
    
    segment = query.order_by(Segment.zone, Segment.id).first()
    
    if not segment:
        zone_msg = f" in zone {zone}" if zone else ""
        logger.warning(f"No available segments in pool{zone_msg}")
        raise HTTPException(status_code=404, detail=f"No available segments in pool{zone_msg}")
    
    logger.info(f"Found available segment: {segment.segment} (VLAN: {segment.vlan_id}) in zone {segment.zone}")
    return segment


@router.post("/segments", response_model=SegmentResponse)
async def create_segment(segment: SegmentCreate, db: Session = Depends(get_db_session)):
    """Create a new segment in the pool with zone-based duplicate validation."""
    logger.info(f"Creating new segment: Zone {segment.zone}, VLAN {segment.vlan_id}, Segment {segment.segment}")
    
    try:
        # Check if VLAN ID already exists in the same zone
        existing_vlan = db.query(Segment).filter(
            and_(Segment.zone == segment.zone, Segment.vlan_id == segment.vlan_id)
        ).first()
        if existing_vlan:
            logger.error(f"Duplicate VLAN ID {segment.vlan_id} in zone {segment.zone} - already exists with ID {existing_vlan.id}")
            raise HTTPException(
                status_code=400, 
                detail=f"VLAN ID {segment.vlan_id} already exists in zone {segment.zone} (segment {existing_vlan.segment}, ID: {existing_vlan.id})"
            )
        
        # Check if segment already exists in the same zone
        existing_segment = db.query(Segment).filter(
            and_(Segment.zone == segment.zone, Segment.segment == segment.segment)
        ).first()
        if existing_segment:
            logger.error(f"Duplicate segment {segment.segment} in zone {segment.zone} - already exists with ID {existing_segment.id}")
            raise HTTPException(
                status_code=400, 
                detail=f"Segment {segment.segment} already exists in zone {segment.zone} (VLAN ID {existing_segment.vlan_id}, ID: {existing_segment.id})"
            )
        
        # Create new segment
        db_segment = Segment(
            zone=segment.zone,
            vlan_id=segment.vlan_id,
            epg_name=segment.epg_name,
            segment=segment.segment,
            cluster_using=segment.cluster_using,
            in_use=bool(segment.cluster_using)  # Auto-set in_use if cluster is provided
        )
        
        db.add(db_segment)
        db.commit()
        db.refresh(db_segment)
        
        logger.info(f"Successfully created segment with ID {db_segment.id}, VLAN {db_segment.vlan_id}")
        return db_segment
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error: {e}")
        if "vlan_id" in str(e):
            raise HTTPException(status_code=400, detail=f"VLAN ID {segment.vlan_id} already exists")
        elif "segment" in str(e):
            raise HTTPException(status_code=400, detail=f"Segment {segment.segment} already exists")
        else:
            raise HTTPException(status_code=400, detail="Duplicate data detected")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating segment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/segments/{segment_id}/allocate", response_model=SegmentResponse)
async def allocate_segment(
    segment_id: int, 
    allocation: SegmentAllocation, 
    db: Session = Depends(get_db_session)
):
    """Allocate a segment to a cluster (mark as in use)."""
    logger.info(f"Allocating segment {segment_id} to cluster {allocation.cluster_name}")
    
    segment = db.query(Segment).filter(Segment.id == segment_id).first()
    
    if not segment:
        logger.error(f"Segment {segment_id} not found")
        raise HTTPException(status_code=404, detail="Segment not found")
    
    if segment.in_use:
        logger.warning(f"Segment {segment_id} already in use by {segment.cluster_using}")
        raise HTTPException(
            status_code=400, 
            detail=f"Segment already in use by cluster: {segment.cluster_using}"
        )
    
    # Check if cluster already has segments allocated
    existing_allocation = db.query(Segment).filter(
        Segment.cluster_using == allocation.cluster_name
    ).first()
    
    if existing_allocation:
        logger.warning(f"Cluster {allocation.cluster_name} already has segment {existing_allocation.id} allocated")
        # This is just a warning, not an error - clusters can have multiple segments
    
    try:
        segment.cluster_using = allocation.cluster_name
        segment.in_use = True
        
        db.commit()
        db.refresh(segment)
        
        logger.info(f"Successfully allocated segment {segment_id} to {allocation.cluster_name}")
        return segment
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error allocating segment {segment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to allocate segment")


@router.post("/segments/{segment_id}/release", response_model=SegmentResponse)
async def release_segment(segment_id: int, db: Session = Depends(get_db_session)):
    """Release a segment (mark as not in use)."""
    logger.info(f"Releasing segment {segment_id}")
    
    segment = db.query(Segment).filter(Segment.id == segment_id).first()
    
    if not segment:
        logger.error(f"Segment {segment_id} not found")
        raise HTTPException(status_code=404, detail="Segment not found")
    
    previous_cluster = segment.cluster_using
    
    try:
        segment.cluster_using = None
        segment.in_use = False
        
        db.commit()
        db.refresh(segment)
        
        logger.info(f"Successfully released segment {segment_id} from {previous_cluster}")
        return segment
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error releasing segment {segment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to release segment")


@router.put("/segments/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: int, 
    segment_update: SegmentUpdate, 
    db: Session = Depends(get_db_session)
):
    """Update a segment's information with duplicate validation."""
    logger.info(f"Updating segment {segment_id}")
    
    segment = db.query(Segment).filter(Segment.id == segment_id).first()
    
    if not segment:
        logger.error(f"Segment {segment_id} not found")
        raise HTTPException(status_code=404, detail="Segment not found")
    
    update_data = segment_update.model_dump(exclude_unset=True)
    
    try:
        # Check for duplicate VLAN ID if being updated
        if 'vlan_id' in update_data and update_data['vlan_id'] != segment.vlan_id:
            existing_vlan = db.query(Segment).filter(
                and_(Segment.vlan_id == update_data['vlan_id'], Segment.id != segment_id)
            ).first()
            if existing_vlan:
                logger.error(f"Cannot update to VLAN ID {update_data['vlan_id']} - already exists")
                raise HTTPException(
                    status_code=400, 
                    detail=f"VLAN ID {update_data['vlan_id']} already exists"
                )
        
        # Check for duplicate segment if being updated
        if 'segment' in update_data and update_data['segment'] != segment.segment:
            existing_segment = db.query(Segment).filter(
                and_(Segment.segment == update_data['segment'], Segment.id != segment_id)
            ).first()
            if existing_segment:
                logger.error(f"Cannot update to segment {update_data['segment']} - already exists")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Segment {update_data['segment']} already exists"
                )
        
        # Apply updates
        for field, value in update_data.items():
            setattr(segment, field, value)
        
        # Update the in_use flag based on cluster_using
        if 'cluster_using' in update_data:
            segment.in_use = bool(update_data['cluster_using'])
        
        db.commit()
        db.refresh(segment)
        
        logger.info(f"Successfully updated segment {segment_id}")
        return segment
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating segment {segment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update segment")


@router.delete("/segments/{segment_id}")
async def delete_segment(segment_id: int, db: Session = Depends(get_db_session)):
    """Delete a segment from the pool."""
    logger.info(f"Deleting segment {segment_id}")
    
    segment = db.query(Segment).filter(Segment.id == segment_id).first()
    
    if not segment:
        logger.error(f"Segment {segment_id} not found")
        raise HTTPException(status_code=404, detail="Segment not found")
    
    if segment.in_use:
        logger.warning(f"Attempted to delete in-use segment {segment_id}")
        raise HTTPException(status_code=400, detail="Cannot delete segment that is in use")
    
    try:
        db.delete(segment)
        db.commit()
        
        logger.info(f"Successfully deleted segment {segment_id}")
        return {"message": f"Segment {segment_id} deleted successfully"}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting segment {segment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete segment")


@router.get("/stats", response_model=SegmentStats)
async def get_statistics(db: Session = Depends(get_db_session)):
    """Get comprehensive statistics about segment usage including per-zone breakdown."""
    logger.info("Fetching segment statistics")
    
    try:
        # Overall statistics
        total = db.query(Segment).count()
        in_use = db.query(Segment).filter(Segment.in_use == True).count()
        available = total - in_use
        
        # Get unique active clusters
        active_clusters = db.query(Segment.cluster_using).filter(
            Segment.cluster_using.isnot(None)
        ).distinct().count()
        
        utilization = round((in_use / total * 100) if total > 0 else 0, 2)
        
        # Per-zone statistics
        zones_data = {}
        zones = db.query(Segment.zone).distinct().all()
        
        for zone_row in zones:
            zone = zone_row[0]
            zone_total = db.query(Segment).filter(Segment.zone == zone).count()
            zone_in_use = db.query(Segment).filter(
                and_(Segment.zone == zone, Segment.in_use == True)
            ).count()
            zone_available = zone_total - zone_in_use
            zone_utilization = round((zone_in_use / zone_total * 100) if zone_total > 0 else 0, 2)
            zone_clusters = db.query(Segment.cluster_using).filter(
                and_(Segment.zone == zone, Segment.cluster_using.isnot(None))
            ).distinct().count()
            
            zones_data[zone] = {
                'total_segments': zone_total,
                'segments_in_use': zone_in_use,
                'segments_available': zone_available,
                'utilization_percentage': zone_utilization,
                'active_clusters': zone_clusters
            }
        
        stats = SegmentStats(
            total_segments=total,
            segments_in_use=in_use,
            segments_available=available,
            utilization_percentage=utilization,
            active_clusters=active_clusters,
            zones=zones_data
        )
        
        logger.info(f"Statistics: {stats.model_dump()}")
        return stats
        
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")


@router.get("/zones", response_model=List[str])
async def get_zones(db: Session = Depends(get_db_session)):
    """Get list of all available zones."""
    logger.info("Fetching available zones")
    
    try:
        zones = db.query(Segment.zone).distinct().order_by(Segment.zone).all()
        zone_list = [zone[0] for zone in zones]
        
        logger.info(f"Found zones: {zone_list}")
        return zone_list
        
    except Exception as e:
        logger.error(f"Error fetching zones: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch zones")


@router.get("/zones/{zone}/stats", response_model=ZoneStats)
async def get_zone_statistics(zone: str, db: Session = Depends(get_db_session)):
    """Get detailed statistics for a specific zone."""
    logger.info(f"Fetching statistics for zone: {zone}")
    
    try:
        # Check if zone exists
        zone_exists = db.query(Segment).filter(Segment.zone == zone).first()
        if not zone_exists:
            raise HTTPException(status_code=404, detail=f"Zone '{zone}' not found")
        
        total = db.query(Segment).filter(Segment.zone == zone).count()
        in_use = db.query(Segment).filter(
            and_(Segment.zone == zone, Segment.in_use == True)
        ).count()
        available = total - in_use
        utilization = round((in_use / total * 100) if total > 0 else 0, 2)
        
        active_clusters = db.query(Segment.cluster_using).filter(
            and_(Segment.zone == zone, Segment.cluster_using.isnot(None))
        ).distinct().count()
        
        stats = ZoneStats(
            zone=zone,
            total_segments=total,
            segments_in_use=in_use,
            segments_available=available,
            utilization_percentage=utilization,
            active_clusters=active_clusters
        )
        
        logger.info(f"Zone {zone} statistics: {stats.model_dump()}")
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching zone statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch zone statistics")