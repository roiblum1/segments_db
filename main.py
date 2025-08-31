"""
Network Segment Management System for OpenShift/Hypershift Clusters
A mini database system with API for managing VLAN segments and EPG configurations
"""

import logging
import re
from datetime import datetime
from typing import Optional, List
from enum import Enum
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import ipaddress

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('segment_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = "sqlite:///./segment_database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class SegmentDB(Base):
    __tablename__ = "segments"
    
    id = Column(Integer, primary_key=True, index=True)
    vlan_id = Column(Integer, unique=True, nullable=False)
    epg_name = Column(String, nullable=False)
    segment = Column(String, unique=True, nullable=False)
    cluster_using = Column(String, nullable=True)
    in_use = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic Models with validation
class SegmentBase(BaseModel):
    vlan_id: int = Field(..., ge=1, le=4094, description="VLAN ID must be between 1 and 4094")
    epg_name: str = Field(..., min_length=1, max_length=100, description="EPG Name")
    segment: str = Field(..., description="Network segment with subnet prefix (e.g., 192.168.1.0/24)")
    cluster_using: Optional[str] = Field(None, description="Cluster name using this segment")
    
    @validator('segment')
    def validate_segment(cls, v):
        """Validate that segment has proper CIDR notation"""
        try:
            # Check if it's a valid CIDR notation
            network = ipaddress.ip_network(v, strict=False)
            # Ensure it has a prefix (not /32 for individual IPs unless intended)
            if '/' not in v:
                raise ValueError("Segment must include subnet prefix (e.g., /24)")
            return str(network)
        except ValueError as e:
            logger.error(f"Invalid segment format: {v}")
            raise ValueError(f"Invalid segment format. Must be valid CIDR notation (e.g., 192.168.1.0/24): {str(e)}")
    
    @validator('cluster_using')
    def validate_cluster_name(cls, v):
        """Validate that cluster name is lowercase"""
        if v is None or v == "":
            return v
        if v != v.lower():
            logger.warning(f"Cluster name converted to lowercase: {v} -> {v.lower()}")
            return v.lower()
        # Additional validation: no spaces, only alphanumeric and hyphens
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError("Cluster name must contain only lowercase letters, numbers, and hyphens")
        return v
    
    @validator('epg_name')
    def validate_epg_name(cls, v):
        """Validate EPG name format"""
        if not v.strip():
            raise ValueError("EPG name cannot be empty")
        # Remove any special characters that might cause issues
        cleaned = re.sub(r'[^\w\s-]', '', v)
        return cleaned.strip()

class SegmentCreate(SegmentBase):
    pass

class SegmentUpdate(BaseModel):
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)
    epg_name: Optional[str] = Field(None, min_length=1, max_length=100)
    segment: Optional[str] = None
    cluster_using: Optional[str] = None
    
    @validator('segment')
    def validate_segment(cls, v):
        if v is None:
            return v
        try:
            network = ipaddress.ip_network(v, strict=False)
            if '/' not in v:
                raise ValueError("Segment must include subnet prefix")
            return str(network)
        except ValueError as e:
            raise ValueError(f"Invalid segment format: {str(e)}")
    
    @validator('cluster_using')
    def validate_cluster_name(cls, v):
        if v is None or v == "":
            return v
        if v != v.lower():
            return v.lower()
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError("Cluster name must contain only lowercase letters, numbers, and hyphens")
        return v

class SegmentResponse(SegmentBase):
    id: int
    in_use: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

class SegmentAllocation(BaseModel):
    cluster_name: str = Field(..., description="Name of the cluster requesting the segment")
    
    @validator('cluster_name')
    def validate_cluster_name(cls, v):
        if v != v.lower():
            return v.lower()
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError("Cluster name must contain only lowercase letters, numbers, and hyphens")
        return v

# Database context manager
@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FastAPI app
app = FastAPI(
    title="Network Segment Manager",
    description="API for managing network segments for OpenShift/Hypershift clusters",
    version="1.0.0"
)

# CORS middleware for UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI"""
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Segment Manager</title>
        </head>
        <body>
            <h1>Network Segment Manager</h1>
            <p>API is running. Access the interactive docs at <a href="/docs">/docs</a></p>
            <p>UI file not found. Please ensure index.html exists in the project directory.</p>
        </body>
        </html>
        """

@app.get("/api/segments", response_model=List[SegmentResponse])
async def get_all_segments(
    in_use: Optional[bool] = Query(None, description="Filter by usage status"),
    cluster: Optional[str] = Query(None, description="Filter by cluster name")
):
    """Get all segments or filter by usage status or cluster"""
    logger.info(f"Fetching segments - in_use: {in_use}, cluster: {cluster}")
    
    with get_db() as db:
        query = db.query(SegmentDB)
        
        if in_use is not None:
            query = query.filter(SegmentDB.in_use == in_use)
        
        if cluster:
            query = query.filter(SegmentDB.cluster_using == cluster.lower())
        
        segments = query.all()
        logger.info(f"Found {len(segments)} segments")
        return segments

@app.get("/api/segments/available", response_model=SegmentResponse)
async def get_available_segment():
    """Get the first available (not in use) segment from the pool"""
    logger.info("Requesting available segment from pool")
    
    with get_db() as db:
        segment = db.query(SegmentDB).filter(
            SegmentDB.in_use == False,
            SegmentDB.cluster_using == None
        ).first()
        
        if not segment:
            logger.warning("No available segments in pool")
            raise HTTPException(status_code=404, detail="No available segments in pool")
        
        logger.info(f"Found available segment: {segment.segment} (VLAN: {segment.vlan_id})")
        return segment

@app.post("/api/segments", response_model=SegmentResponse)
async def create_segment(segment: SegmentCreate):
    """Create a new segment in the pool"""
    logger.info(f"Creating new segment: VLAN {segment.vlan_id}, Segment {segment.segment}")
    
    with get_db() as db:
        # Check if VLAN ID or segment already exists
        existing_vlan = db.query(SegmentDB).filter(SegmentDB.vlan_id == segment.vlan_id).first()
        if existing_vlan:
            logger.error(f"VLAN ID {segment.vlan_id} already exists")
            raise HTTPException(status_code=400, detail=f"VLAN ID {segment.vlan_id} already exists")
        
        existing_segment = db.query(SegmentDB).filter(SegmentDB.segment == segment.segment).first()
        if existing_segment:
            logger.error(f"Segment {segment.segment} already exists")
            raise HTTPException(status_code=400, detail=f"Segment {segment.segment} already exists")
        
        db_segment = SegmentDB(
            vlan_id=segment.vlan_id,
            epg_name=segment.epg_name,
            segment=segment.segment,
            cluster_using=segment.cluster_using,
            in_use=bool(segment.cluster_using)
        )
        
        db.add(db_segment)
        db.commit()
        db.refresh(db_segment)
        
        logger.info(f"Successfully created segment with ID {db_segment.id}")
        return db_segment

@app.post("/api/segments/{segment_id}/allocate", response_model=SegmentResponse)
async def allocate_segment(segment_id: int, allocation: SegmentAllocation):
    """Allocate a segment to a cluster (mark as in use)"""
    logger.info(f"Allocating segment {segment_id} to cluster {allocation.cluster_name}")
    
    with get_db() as db:
        segment = db.query(SegmentDB).filter(SegmentDB.id == segment_id).first()
        
        if not segment:
            logger.error(f"Segment {segment_id} not found")
            raise HTTPException(status_code=404, detail="Segment not found")
        
        if segment.in_use:
            logger.warning(f"Segment {segment_id} already in use by {segment.cluster_using}")
            raise HTTPException(
                status_code=400, 
                detail=f"Segment already in use by cluster: {segment.cluster_using}"
            )
        
        segment.cluster_using = allocation.cluster_name
        segment.in_use = True
        segment.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(segment)
        
        logger.info(f"Successfully allocated segment {segment_id} to {allocation.cluster_name}")
        return segment

@app.post("/api/segments/{segment_id}/release", response_model=SegmentResponse)
async def release_segment(segment_id: int):
    """Release a segment (mark as not in use)"""
    logger.info(f"Releasing segment {segment_id}")
    
    with get_db() as db:
        segment = db.query(SegmentDB).filter(SegmentDB.id == segment_id).first()
        
        if not segment:
            logger.error(f"Segment {segment_id} not found")
            raise HTTPException(status_code=404, detail="Segment not found")
        
        previous_cluster = segment.cluster_using
        segment.cluster_using = None
        segment.in_use = False
        segment.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(segment)
        
        logger.info(f"Successfully released segment {segment_id} from {previous_cluster}")
        return segment

@app.put("/api/segments/{segment_id}", response_model=SegmentResponse)
async def update_segment(segment_id: int, segment_update: SegmentUpdate):
    """Update a segment's information"""
    logger.info(f"Updating segment {segment_id}")
    
    with get_db() as db:
        segment = db.query(SegmentDB).filter(SegmentDB.id == segment_id).first()
        
        if not segment:
            logger.error(f"Segment {segment_id} not found")
            raise HTTPException(status_code=404, detail="Segment not found")
        
        update_data = segment_update.dict(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(segment, field, value)
        
        # Update the in_use flag based on cluster_using
        if 'cluster_using' in update_data:
            segment.in_use = bool(update_data['cluster_using'])
        
        segment.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(segment)
        
        logger.info(f"Successfully updated segment {segment_id}")
        return segment

@app.delete("/api/segments/{segment_id}")
async def delete_segment(segment_id: int):
    """Delete a segment from the pool"""
    logger.info(f"Deleting segment {segment_id}")
    
    with get_db() as db:
        segment = db.query(SegmentDB).filter(SegmentDB.id == segment_id).first()
        
        if not segment:
            logger.error(f"Segment {segment_id} not found")
            raise HTTPException(status_code=404, detail="Segment not found")
        
        if segment.in_use:
            logger.warning(f"Attempted to delete in-use segment {segment_id}")
            raise HTTPException(status_code=400, detail="Cannot delete segment that is in use")
        
        db.delete(segment)
        db.commit()
        
        logger.info(f"Successfully deleted segment {segment_id}")
        return {"message": "Segment deleted successfully"}

@app.get("/api/stats")
async def get_statistics():
    """Get statistics about segment usage"""
    logger.info("Fetching segment statistics")
    
    with get_db() as db:
        total = db.query(SegmentDB).count()
        in_use = db.query(SegmentDB).filter(SegmentDB.in_use == True).count()
        available = db.query(SegmentDB).filter(SegmentDB.in_use == False).count()
        
        clusters = db.query(SegmentDB.cluster_using).filter(
            SegmentDB.cluster_using != None
        ).distinct().all()
        
        stats = {
            "total_segments": total,
            "segments_in_use": in_use,
            "segments_available": available,
            "utilization_percentage": round((in_use / total * 100) if total > 0 else 0, 2),
            "active_clusters": len(clusters)
        }
        
        logger.info(f"Statistics: {stats}")
        return stats

# Initialize with sample data if database is empty
@app.on_event("startup")
async def startup_event():
    """Initialize database with sample data if empty"""
    logger.info("Starting Network Segment Manager")
    
    with get_db() as db:
        count = db.query(SegmentDB).count()
        
        if count == 0:
            logger.info("Database empty, initializing with sample data")
            
            sample_segments = [
                SegmentDB(vlan_id=100, epg_name="Production-EPG", segment="10.100.0.0/24", cluster_using=None, in_use=False),
                SegmentDB(vlan_id=101, epg_name="Production-EPG", segment="10.100.1.0/24", cluster_using=None, in_use=False),
                SegmentDB(vlan_id=102, epg_name="Development-EPG", segment="10.101.0.0/24", cluster_using="dev-cluster-1", in_use=True),
                SegmentDB(vlan_id=103, epg_name="Development-EPG", segment="10.101.1.0/24", cluster_using=None, in_use=False),
                SegmentDB(vlan_id=104, epg_name="Testing-EPG", segment="10.102.0.0/24", cluster_using=None, in_use=False),
            ]
            
            for segment in sample_segments:
                db.add(segment)
            
            db.commit()
            logger.info(f"Initialized database with {len(sample_segments)} sample segments")

if __name__ == "__main__":
    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)