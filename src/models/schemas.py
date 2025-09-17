from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
import ipaddress

class Segment(BaseModel):
    site: str
    vlan_id: int = Field(ge=1, le=4094)
    epg_name: str
    segment: str  # e.g., "192.168.1.0/24"
    description: Optional[str] = ""
    cluster_name: Optional[str] = None  # None means available
    allocated_at: Optional[datetime] = None
    released: bool = False
    released_at: Optional[datetime] = None

class VLANAllocationRequest(BaseModel):
    cluster_name: str
    site: str

class VLANAllocationResponse(BaseModel):
    vlan_id: int
    cluster_name: str
    site: str
    segment: str
    epg_name: str
    allocated_at: datetime

class VLANRelease(BaseModel):
    cluster_name: str
    site: str

class SegmentCreate(BaseModel):
    site: str
    vlan_id: int = Field(ge=1, le=4094)
    epg_name: str
    segment: str
    description: Optional[str] = ""
    
    @validator('segment')
    def validate_segment_prefix(cls, segment, values):
        """Validate that segment IP matches site prefix"""
        site = values.get('site')
        if not site:
            return segment
            
        from src.config.settings import get_site_prefix
        expected_prefix = get_site_prefix(site)
        
        try:
            # First validate that the segment includes explicit subnet mask
            if '/' not in segment:
                raise ValueError(
                    f"Invalid network format. Segment must include subnet mask (e.g., '{segment}/24')"
                )
            
            # Then validate that the segment is in proper network format
            # Parse with strict=True to ensure it's a proper network address
            try:
                ipaddress.ip_network(segment, strict=True)
            except ipaddress.AddressValueError:
                # If strict parsing fails, get the correct network address
                network_loose = ipaddress.ip_network(segment, strict=False)
                correct_format = str(network_loose)
                raise ValueError(
                    f"Invalid network format. Use network address '{correct_format}' instead of '{segment}'"
                )
            
            # Parse the network segment for site prefix validation
            network = ipaddress.ip_network(segment, strict=False)
            first_octet = str(network.network_address).split('.')[0]
            
            if first_octet != expected_prefix:
                raise ValueError(
                    f"Invalid IP prefix for site '{site}'. "
                    f"Expected to start with '{expected_prefix}', got '{first_octet}'"
                )
        except ipaddress.AddressValueError:
            raise ValueError("Invalid IP network format")
            
        return segment