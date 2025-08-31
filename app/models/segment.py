"""
Database models for network segments.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from sqlalchemy.sql import func

from app.core.database import Base


class Segment(Base):
    """Network segment model with enhanced validation, indexing, and zone support."""
    
    __tablename__ = "segments"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Zone/Office location
    zone = Column(String(50), nullable=False, index=True, default="Office1")
    
    # Network configuration
    vlan_id = Column(Integer, nullable=False, index=True)
    epg_name = Column(String(100), nullable=False, index=True)
    segment = Column(String(18), nullable=False, index=True)  # CIDR notation
    
    # Cluster assignment
    cluster_using = Column(String(100), nullable=True, index=True)
    in_use = Column(Boolean, default=False, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Indexes for performance
    __table_args__ = (
        Index('ix_segments_zone_vlan', 'zone', 'vlan_id'),
        Index('ix_segments_zone_segment', 'zone', 'segment'),
        Index('ix_segments_in_use_cluster', 'in_use', 'cluster_using'),
        Index('ix_segments_zone_in_use', 'zone', 'in_use'),
        # Unique constraint: VLAN ID must be unique within each zone
        Index('uq_vlan_per_zone', 'zone', 'vlan_id', unique=True),
        # Unique constraint: Segment must be unique within each zone
        Index('uq_segment_per_zone', 'zone', 'segment', unique=True),
    )
    
    def __repr__(self):
        return f"<Segment(id={self.id}, zone='{self.zone}', vlan_id={self.vlan_id}, segment='{self.segment}', in_use={self.in_use})>"
    
    def to_dict(self):
        """Convert model to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'zone': self.zone,
            'vlan_id': self.vlan_id,
            'epg_name': self.epg_name,
            'segment': self.segment,
            'cluster_using': self.cluster_using,
            'in_use': self.in_use,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }