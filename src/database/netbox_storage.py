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
    CACHE_KEY_REDBULL_TENANT_ID, CACHE_KEY_TENANT_REDBULL
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
            set_cache(f"site_group_{sg.id}", sg, ttl=3600)
        logger.info(f"Cached {len(site_groups)} site groups")

        # Pre-fetch RedBull tenant
        tenant = await run_netbox_get(
            lambda: nb.tenancy.tenants.get(slug=TENANT_REDBULL_SLUG),
            f"prefetch {TENANT_REDBULL} tenant"
        )
        if tenant:
            set_cache(CACHE_KEY_REDBULL_TENANT_ID, tenant.id, ttl=3600)
            set_cache(CACHE_KEY_TENANT_REDBULL, tenant, ttl=3600)
            logger.info(f"Cached {TENANT_REDBULL} tenant (ID: {tenant.id})")

        # Pre-fetch roles
        role_data = await run_netbox_get(
            lambda: nb.ipam.roles.get(name=ROLE_DATA),
            f"prefetch {ROLE_DATA} role"
        )
        if role_data:
            set_cache("role_data", role_data, ttl=3600)
            logger.info(f"Cached Data role (ID: {role_data.id})")

        # Pre-fetch VRFs
        vrfs = await run_netbox_get(
            lambda: list(nb.ipam.vrfs.all()),
            "prefetch VRFs"
        )
        vrf_names = [vrf.name for vrf in vrfs]
        set_cache("vrfs", vrf_names, ttl=3600)
        logger.info(f"Cached {len(vrf_names)} VRFs")

    except Exception as e:
        logger.error(f"Error pre-fetching reference data: {e}", exc_info=True)


async def sync_netbox_vlans():
    """Sync existing VLANs from NetBox with RedBull tenant"""
    try:
        nb = get_netbox_client()
        logger.info(f"Syncing existing VLANs from NetBox (Tenant: {TENANT_REDBULL})")

        tenant = await run_netbox_get(
            lambda: nb.tenancy.tenants.get(slug=TENANT_REDBULL_SLUG),
            f"get {TENANT_REDBULL} tenant"
        )
        if not tenant:
            logger.warning(f"{TENANT_REDBULL} tenant not found - skipping VLAN sync")
            return

        vlans = await run_netbox_get(
            lambda: list(nb.ipam.vlans.filter(tenant_id=tenant.id)),
            f"get VLANs with {TENANT_REDBULL} tenant"
        )

        if not vlans:
            logger.info(f"No existing VLANs found with {TENANT_REDBULL} tenant")
            return

        logger.info(f"Found {len(vlans)} VLANs - syncing...")

        # Fetch all prefixes in one call
        all_prefixes = await run_netbox_get(
            lambda: list(nb.ipam.prefixes.filter(tenant_id=tenant.id)),
            f"get all prefixes for {TENANT_REDBULL} tenant"
        )

        # Build map: vlan_id → prefix
        prefix_by_vlan = {}
        for prefix in all_prefixes:
            vlan_id = safe_get_id(safe_get_attr(prefix, 'vlan'))
            if vlan_id and vlan_id not in prefix_by_vlan:
                prefix_by_vlan[vlan_id] = prefix

        synced_count = 0
        for vlan in vlans:
            try:
                prefix = prefix_by_vlan.get(vlan.id)
                if not prefix:
                    continue

                # Extract site from prefix scope using cached site groups
                site_name = get_site_slug_from_prefix(prefix)
                if not site_name or not safe_get_attr(prefix, 'vrf'):
                    continue

                synced_count += 1
            except Exception as e:
                logger.error(f"Error syncing VLAN {vlan.vid}: {e}")
                continue

        logger.info(f"VLAN sync complete: {synced_count} synced")

    except Exception as e:
        logger.error(f"Error during VLAN sync: {e}", exc_info=True)


async def init_storage():
    """Initialize NetBox storage - verify connection and sync existing data"""
    try:
        nb = get_netbox_client()
        status = await run_netbox_get(lambda: nb.status(), "get NetBox status")
        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")

        await prefetch_reference_data()
        await sync_netbox_vlans()

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

    async def find_one_optimized(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await self.query_ops.find_one_optimized(query)

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
