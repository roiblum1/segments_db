from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class Segment(BaseModel):
    site: str
    vlan_id: int = Field(ge=1, le=4094)
    epg_name: str
    segment: str  # e.g., "192.168.1.0/24"
    vrf: str  # VRF name (e.g., "Network1", "Network2", "Network3")
    dhcp: bool = False  # DHCP enabled/disabled
    description: Optional[str] = ""  # Kept for backward compatibility
    cluster_name: Optional[str] = None  # None means available
    allocated_at: Optional[datetime] = None
    released: bool = False
    released_at: Optional[datetime] = None

class VLANAllocationRequest(BaseModel):
    cluster_name: str
    site: str
    vrf: str  # Required: VRF/Network to allocate from

class VLANAllocationResponse(BaseModel):
    vlan_id: int
    cluster_name: str
    site: str
    segment: str
    epg_name: str
    vrf: str  # Include VRF in response
    allocated_at: datetime

class VLANRelease(BaseModel):
    cluster_name: str
    site: str

