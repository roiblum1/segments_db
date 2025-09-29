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

