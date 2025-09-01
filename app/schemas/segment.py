"""
Pydantic schemas for request/response validation.
"""
import re
from datetime import datetime
from typing import Optional
import ipaddress

from pydantic import BaseModel, Field, field_validator

from app.core.logging import get_logger

logger = get_logger("schemas")


class SegmentBase(BaseModel):
    """Base segment schema with validation and zone support."""
    
    zone: str = Field(..., min_length=1, max_length=50, description="Office zone (e.g., Office1, Office2, Office3)")
    vlan_id: int = Field(..., ge=1, le=4094, description="VLAN ID must be between 1 and 4094 (unique per zone)")
    epg_name: str = Field(..., min_length=1, max_length=100, description="EPG Name")
    segment: str = Field(..., description="Network segment with subnet prefix (e.g., 192.168.1.0/24)")
    cluster_using: Optional[str] = Field(None, description="Cluster name using this segment")
    
    @field_validator('segment')
    @classmethod
    def validate_segment(cls, v: str) -> str:
        """Validate that segment has proper CIDR notation."""
        if not v:
            raise ValueError("Segment cannot be empty")
        
        try:
            # Check if it's a valid CIDR notation
            network = ipaddress.ip_network(v, strict=False)
            # Ensure it has a prefix (not /32 for individual IPs unless intended)
            if '/' not in v:
                raise ValueError("Segment must include subnet prefix (e.g., /24)")
            
            # Log validation success
            logger.debug(f"Validated segment: {v} -> {network}")
            return str(network)
        except ValueError as e:
            logger.error(f"Invalid segment format: {v}, error: {e}")
            raise ValueError(f"Invalid segment format. Must be valid CIDR notation (e.g., 192.168.1.0/24): {str(e)}")
    
    @field_validator('cluster_using')
    @classmethod
    def validate_cluster_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate that cluster name is lowercase and follows naming conventions."""
        if v is None or v == "":
            return v
        
        # Convert to lowercase
        v_lower = v.lower()
        if v != v_lower:
            logger.info(f"Cluster name converted to lowercase: {v} -> {v_lower}")
        
        # Additional validation: no spaces, only alphanumeric and hyphens
        if not re.match(r'^[a-z0-9-]+$', v_lower):
            logger.error(f"Invalid cluster name format: {v_lower}")
            raise ValueError("Cluster name must contain only lowercase letters, numbers, and hyphens")
        
        return v_lower
    
    @field_validator('epg_name')
    @classmethod
    def validate_epg_name(cls, v: str) -> str:
        """Validate EPG name format."""
        if not v or not v.strip():
            raise ValueError("EPG name cannot be empty")
        
        # Remove any special characters that might cause issues
        cleaned = re.sub(r'[^\w\s-]', '', v)
        cleaned = cleaned.strip()
        
        if not cleaned:
            raise ValueError("EPG name must contain valid characters")
        
        logger.debug(f"Validated EPG name: {v} -> {cleaned}")
        return cleaned
    
    @field_validator('zone')
    @classmethod
    def validate_zone(cls, v: str) -> str:
        """Validate zone name format."""
        if not v or not v.strip():
            raise ValueError("Zone cannot be empty")
        
        # Clean and validate zone name
        cleaned = v.strip()
        
        # Allow alphanumeric characters, spaces, hyphens, and underscores
        if not re.match(r'^[a-zA-Z0-9\s\-_]+$', cleaned):
            raise ValueError("Zone name must contain only letters, numbers, spaces, hyphens, and underscores")
        
        logger.debug(f"Validated zone: {v} -> {cleaned}")
        return cleaned


class SegmentCreate(SegmentBase):
    """Schema for creating a new segment."""
    pass


class SegmentUpdate(BaseModel):
    """Schema for updating an existing segment."""
    
    zone: Optional[str] = Field(None, min_length=1, max_length=50)
    vlan_id: Optional[int] = Field(None, ge=1, le=4094)
    epg_name: Optional[str] = Field(None, min_length=1, max_length=100)
    segment: Optional[str] = None
    cluster_using: Optional[str] = None
    
    @field_validator('segment')
    @classmethod
    def validate_segment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return SegmentBase.validate_segment(v)
    
    @field_validator('cluster_using')
    @classmethod
    def validate_cluster_name(cls, v: Optional[str]) -> Optional[str]:
        return SegmentBase.validate_cluster_name(v)
    
    @field_validator('epg_name')
    @classmethod
    def validate_epg_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return SegmentBase.validate_epg_name(v)
    
    @field_validator('zone')
    @classmethod
    def validate_zone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return SegmentBase.validate_zone(v)


class SegmentResponse(SegmentBase):
    """Schema for segment response."""
    
    id: int
    in_use: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SegmentAllocation(BaseModel):
    """Schema for segment allocation requests."""
    
    cluster_name: str = Field(..., description="Name of the cluster requesting the segment")
    
    @field_validator('cluster_name')
    @classmethod
    def validate_cluster_name(cls, v: str) -> str:
        return SegmentBase.validate_cluster_name(v)


class ZoneAllocationRequest(BaseModel):
    """Schema for zone-based automatic segment allocation requests."""
    
    zone: str = Field(..., min_length=1, max_length=50, description="Zone where segment should be allocated")
    cluster_name: str = Field(..., description="Name of the cluster requesting the segment")
    
    @field_validator('cluster_name')
    @classmethod
    def validate_cluster_name(cls, v: str) -> str:
        return SegmentBase.validate_cluster_name(v)
    
    @field_validator('zone')
    @classmethod
    def validate_zone(cls, v: str) -> str:
        return SegmentBase.validate_zone(v)


class SegmentStats(BaseModel):
    """Schema for segment statistics."""
    
    total_segments: int
    segments_in_use: int
    segments_available: int
    utilization_percentage: float
    active_clusters: int
    zones: dict[str, dict[str, int]] = Field(default_factory=dict, description="Per-zone statistics")


class ZoneStats(BaseModel):
    """Schema for per-zone statistics."""
    
    zone: str
    total_segments: int
    segments_in_use: int
    segments_available: int
    utilization_percentage: float
    active_clusters: int