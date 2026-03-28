"""
NetBox Storage Lifecycle

This module provides only the three lifecycle functions:
- init_storage(): Connect to NetBox, wire the segments module, prefetch reference data.
- close_storage(): Cleanup NetBox client.
- prefetch_reference_data(): Pre-warm the caches for reference objects.

The NetBoxStorage class and get_storage() factory have been removed.
All segment operations are now in netbox_segments.py.
"""

import logging

from .netbox_client import get_netbox_client, close_netbox_client, run_netbox_get
from .netbox_cache import set_cache
from .netbox_constants import (
    TENANT_REDBULL, TENANT_REDBULL_SLUG, ROLE_DATA,
    CACHE_KEY_REDBULL_TENANT_ID, CACHE_KEY_TENANT_REDBULL,
    CACHE_TTL_LONG,
)
from .netbox_segments import init_segments_module

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
    """Initialize NetBox storage - verify connection, wire modules, prefetch reference data"""
    try:
        nb = get_netbox_client()
        status = await run_netbox_get(lambda: nb.status(), "get NetBox status")
        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")
        init_segments_module(nb)           # Wire segments module to client
        await prefetch_reference_data()
    except Exception as e:
        logger.error(f"Failed to connect to NetBox: {e}", exc_info=True)
        raise


async def close_storage():
    """Close NetBox storage - cleanup if needed"""
    close_netbox_client()
