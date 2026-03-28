"""
Database module - NetBox storage implementation

Domain-named interface for segment operations.
"""

from .netbox_storage import init_storage, close_storage
from .netbox_segments import (
    get_segments,
    get_segment_by_id,
    create_segment,
    update_segment,
    delete_segment,
    allocate_segment,
    get_vrfs,
)

__all__ = [
    'init_storage',
    'close_storage',
    'get_segments',
    'get_segment_by_id',
    'create_segment',
    'update_segment',
    'delete_segment',
    'allocate_segment',
    'get_vrfs',
]
