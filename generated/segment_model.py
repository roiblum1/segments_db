"""
Auto-generated Pydantic models from segment_schema.py
DO NOT EDIT DIRECTLY - Run scripts/generate_schema.py to regenerate
"""
from pydantic import BaseModel, Field
from typing import Optional


class Segment(BaseModel):
    """Segment model for API requests"""
    site: str = annotation=NoneType required=True description='Site name (e.g., Site1, Site2, Site3)'
    vlan_id: int = annotation=NoneType required=True description='VLAN ID (1-4094)'
    epg_name: str = annotation=NoneType required=True description='EPG/VLAN name'
    segment: str = annotation=NoneType required=True description='Network segment (e.g., 192.1.1.0/24)'
    dhcp: bool = annotation=NoneType required=False default=False description='DHCP enabled'
    description: str = annotation=NoneType required=False default='' description='Segment description/comments'

    class Config:
        json_schema_extra = {
            "example": {
                "site": "Site1",
                "vlan_id": 100,
                "epg_name": "EPG_PROD_01",
                "segment": "192.1.1.0/24",
                "dhcp": True,
                "description": "Production network"
            }
        }