"""
NetBox Storage Implementation

This module provides a storage interface that uses NetBox's REST API
for managing VLANs and IP prefixes (segments).
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from .netbox_client import get_netbox_client, close_netbox_client, run_netbox_get
from .netbox_helpers import NetBoxHelpers
from .netbox_query_ops import NetBoxQueryOps
from .netbox_crud_ops import NetBoxCRUDOps
from .netbox_cache import get_cached, set_cache
from .netbox_utils import safe_get_id, safe_get_attr, get_site_slug_from_prefix
from .netbox_constants import (
    TENANT_REDBULL, TENANT_REDBULL_SLUG, ROLE_DATA,
    CACHE_KEY_REDBULL_TENANT_ID, CACHE_KEY_TENANT_REDBULL,
    CACHE_TTL_LONG
)

logger = logging.getLogger(__name__)


async def prefetch_reference_data():
    """Pre-fetch and cache reference data that rarely changes"""
    try:
        nb = get_netbox_client()
        logger.info("Pre-fetching reference data...")

        # Pre-fetch all site groups
        site_groups = await run_netbox_get(
            lambda: list(nb.dcim.site_groups.all()),
            "prefetch all site groups"
        )
        for sg in site_groups:
            set_cache(f"site_group_{sg.id}", sg, ttl=CACHE_TTL_LONG)
        logger.info(f"Cached {len(site_groups)} site groups")

        # Pre-fetch RedBull tenant
        tenant = await run_netbox_get(
            lambda: nb.tenancy.tenants.get(slug=TENANT_REDBULL_SLUG),
            f"prefetch {TENANT_REDBULL} tenant"
        )
        if tenant:
            set_cache(CACHE_KEY_REDBULL_TENANT_ID, tenant.id, ttl=CACHE_TTL_LONG)
            set_cache(CACHE_KEY_TENANT_REDBULL, tenant, ttl=CACHE_TTL_LONG)
            logger.info(f"Cached {TENANT_REDBULL} tenant (ID: {tenant.id})")

        # Pre-fetch roles
        role_data = await run_netbox_get(
            lambda: nb.ipam.roles.get(name=ROLE_DATA),
            f"prefetch {ROLE_DATA} role"
        )
        if role_data:
            set_cache("role_data", role_data, ttl=CACHE_TTL_LONG)
            logger.info(f"Cached Data role (ID: {role_data.id})")

        # Pre-fetch VRFs
        vrfs = await run_netbox_get(
            lambda: list(nb.ipam.vrfs.all()),
            "prefetch VRFs"
        )
        vrf_names = [vrf.name for vrf in vrfs]
        set_cache("vrfs", vrf_names, ttl=CACHE_TTL_LONG)
        logger.info(f"Cached {len(vrf_names)} VRFs")

    except Exception as e:
        logger.error(f"Error pre-fetching reference data: {e}", exc_info=True)


async def init_storage():
    """Initialize NetBox storage - verify connection and prefetch reference data"""
    try:
        nb = get_netbox_client()
        status = await run_netbox_get(lambda: nb.status(), "get NetBox status")
        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")

        await prefetch_reference_data()

    except Exception as e:
        logger.error(f"Failed to connect to NetBox: {e}", exc_info=True)
        raise


async def close_storage():
    """Close NetBox storage - cleanup if needed"""
    close_netbox_client()


class NetBoxStorage:
    """NetBox Storage Implementation"""

    def __init__(self):
        self.nb = get_netbox_client()
        self.helpers = NetBoxHelpers(self.nb)
        self.query_ops = NetBoxQueryOps(self.nb, self.helpers)
        self.crud_ops = NetBoxCRUDOps(self.nb, self.helpers, self.query_ops)

    # Query Operations
    async def find(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return await self.query_ops.find(query)

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self.query_ops.find_one(query)

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        return await self.query_ops.count_documents(query)

    # CRUD Operations
    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        return await self.crud_ops.insert_one(document)

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        return await self.crud_ops.update_one(query, update)

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        return await self.crud_ops.delete_one(query)

    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        sort: Optional[List[tuple]] = None
    ) -> Optional[Dict[str, Any]]:
        return await self.crud_ops.find_one_and_update(query, update, sort)

    async def get_vrfs(self) -> List[str]:
        return await self.helpers.get_vrfs()


def get_storage() -> NetBoxStorage:
    """Get the NetBox storage instance"""
    return NetBoxStorage()
