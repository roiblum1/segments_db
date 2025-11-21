"""
NetBox Storage Implementation

This module provides a storage interface that uses NetBox's REST API
for managing VLANs and IP prefixes (segments). It replaces the local
JSON file storage with NetBox as the backend.

NetBox Objects Used:
- Sites (dcim.sites): Locations/data centers
- VLANs (ipam.vlans): VLAN definitions
- Prefixes (ipam.prefixes): IP address segments/subnets
- Custom Fields: cluster_name, allocated_at, released, released_at, description

This module has been refactored into smaller, focused modules:
- netbox_client.py: Client initialization and executors
- netbox_cache.py: Cache management
- netbox_helpers.py: Helper functions for NetBox objects
- netbox_converters.py: Data conversion functions
- netbox_sync.py: Initialization and sync functions
- netbox_query_ops.py: Read operations (find, count)
- netbox_crud_ops.py: Write operations (insert, update, delete)
"""

import logging
from typing import Optional, List, Dict, Any

from .netbox_client import get_netbox_client
from .netbox_helpers import NetBoxHelpers
from .netbox_query_ops import NetBoxQueryOps
from .netbox_crud_ops import NetBoxCRUDOps

logger = logging.getLogger(__name__)


class NetBoxStorage:
    """
    NetBox Storage Implementation

    Maps our segment/VLAN data model to NetBox's IPAM model:
    - Segment = NetBox Prefix (IP subnet)
    - VLAN ID = NetBox VLAN
    - Site = NetBox Site
    - EPG Name = Stored in Prefix description/custom field
    - Cluster allocation = Custom field on Prefix

    This class now delegates to specialized operation classes:
    - NetBoxQueryOps: Read operations
    - NetBoxCRUDOps: Write operations
    """

    def __init__(self):
        self.nb = get_netbox_client()
        self.helpers = NetBoxHelpers(self.nb)
        self.query_ops = NetBoxQueryOps(self.nb, self.helpers)
        self.crud_ops = NetBoxCRUDOps(self.nb, self.helpers, self.query_ops)

    # ============================================================================
    # Query Operations (delegated to NetBoxQueryOps)
    # ============================================================================

    async def find(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Find segments matching the query"""
        return await self.query_ops.find(query)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        return await self.query_ops.find_one(query)

    async def find_one_optimized(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Optimized find_one for allocation queries"""
        return await self.query_ops.find_one_optimized(query)

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        """Count segments matching the query"""
        return await self.query_ops.count_documents(query)

    # ============================================================================
    # CRUD Operations (delegated to NetBoxCRUDOps)
    # ============================================================================

    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new segment in NetBox"""
        return await self.crud_ops.insert_one(document)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a segment in NetBox"""
        return await self.crud_ops.update_one(query, update)

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment from NetBox"""
        return await self.crud_ops.delete_one(query)

    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        sort: Optional[List[tuple]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find and update a segment atomically"""
        return await self.crud_ops.find_one_and_update(query, update, sort)

    # ============================================================================
    # Helper Methods
    # ============================================================================

    async def get_vrfs(self) -> List[str]:
        """Get list of available VRFs from NetBox (cached for 1 hour)"""
        return await self.helpers.get_vrfs()


def get_storage() -> NetBoxStorage:
    """Get the NetBox storage instance"""
    return NetBoxStorage()


# Re-export sync functions for backward compatibility
from .netbox_sync import init_storage, close_storage
