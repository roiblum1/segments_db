"""
Database module - NetBox storage implementation

Maintains backward compatibility by exporting the same interface
as before the refactoring.
"""

from .netbox_storage import NetBoxStorage, get_storage
from .netbox_sync import init_storage, close_storage

__all__ = [
    'NetBoxStorage',
    'get_storage',
    'init_storage',
    'close_storage',
]

