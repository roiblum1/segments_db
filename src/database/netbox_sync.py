"""
NetBox Sync Functions

This module provides initialization and synchronization functions for NetBox storage.
"""

import logging

from .netbox_client import get_netbox_client, close_netbox_client
from .netbox_cache import invalidate_cache, set_cache
from .netbox_utils import run_netbox_get

logger = logging.getLogger(__name__)


async def prefetch_reference_data():
    """Pre-fetch and cache reference data that rarely changes

    This CRITICAL optimization prevents API spam by caching:
    - All site groups (used in prefix_to_segment conversion)
    - Tenant ID (used in every query)
    - Roles (used in VLAN/Prefix creation)
    - VRFs (used in VLAN allocation)

    Without this pre-fetch, listing 100 segments would make 100+ extra API calls
    just to fetch site groups.
    """
    try:
        nb = get_netbox_client()
        logger.info("Pre-fetching reference data to populate cache...")

        # 1. Pre-fetch all site groups (CRITICAL - prevents 100+ API calls per segment list)
        logger.info("Pre-fetching site groups...")
        site_groups = await run_netbox_get(
            lambda: list(nb.dcim.site_groups.all()),
            "prefetch all site groups"
        )
        for sg in site_groups:
            cache_key = f"site_group_{sg.id}"
            set_cache(cache_key, sg, ttl=300)  # 5 minutes
        logger.info(f"Cached {len(site_groups)} site groups")

        # 2. Pre-fetch RedBull tenant
        logger.info("Pre-fetching RedBull tenant...")
        tenant = await run_netbox_get(
            lambda: nb.tenancy.tenants.get(slug="redbull"),
            "prefetch RedBull tenant"
        )
        if tenant:
            set_cache("redbull_tenant_id", tenant.id, ttl=300)
            set_cache("tenant_redbull", tenant, ttl=300)
            logger.info(f"Cached RedBull tenant (ID: {tenant.id})")
        else:
            logger.warning("RedBull tenant not found in NetBox")

        # 3. Pre-fetch roles (Data role for both VLAN and Prefix)
        logger.info("Pre-fetching roles...")
        role_data = await run_netbox_get(
            lambda: nb.ipam.roles.get(name="Data"),
            "prefetch Data role"
        )
        if role_data:
            set_cache("role_data", role_data, ttl=300)
            logger.info(f"Cached Data role (ID: {role_data.id})")
        else:
            logger.warning("Data role not found in NetBox")

        # 4. Pre-fetch VRFs
        logger.info("Pre-fetching VRFs...")
        vrfs = await run_netbox_get(
            lambda: list(nb.ipam.vrfs.all()),
            "prefetch VRFs"
        )
        vrf_names = [vrf.name for vrf in vrfs]
        set_cache("vrfs", vrf_names, ttl=300)
        logger.info(f"Cached {len(vrf_names)} VRFs: {vrf_names}")

        logger.info(f"✅ Reference data pre-fetch complete - cached {len(site_groups)} site groups, "
                   f"{len(vrf_names)} VRFs, tenant, and roles")

    except Exception as e:
        logger.error(f"Error pre-fetching reference data: {e}", exc_info=True)
        # Don't raise - allow application to start even if pre-fetch fails
        # The cache will be populated on-demand, just less efficiently


async def init_storage():
    """Initialize NetBox storage - verify connection and sync existing data"""
    try:
        nb = get_netbox_client()

        # Test connection by getting status
        status = await run_netbox_get(lambda: nb.status(), "get NetBox status")

        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")
        from ..config.settings import NETBOX_URL
        logger.info(f"NetBox URL: {NETBOX_URL}")

        # Pre-fetch reference data to warm up cache (CRITICAL for performance)
        await prefetch_reference_data()

        # Sync existing VLANs from NetBox with RedBull tenant
        await sync_netbox_vlans()

    except Exception as e:
        logger.error(f"Failed to connect to NetBox: {e}", exc_info=True)
        raise


async def sync_netbox_vlans():
    """Sync existing VLANs from NetBox with RedBull tenant"""
    try:
        nb = get_netbox_client()

        logger.info("Starting sync of existing VLANs from NetBox (Tenant: RedBull)")

        # Get RedBull tenant
        tenant = await run_netbox_get(lambda: nb.tenancy.tenants.get(slug="redbull"), "get RedBull tenant")
        if not tenant:
            logger.warning("RedBull tenant not found in NetBox - skipping VLAN sync")
            return

        logger.info(f"Found RedBull tenant (ID: {tenant.id})")

        # Get all VLANs with RedBull tenant
        vlans = await run_netbox_get(
            lambda: list(nb.ipam.vlans.filter(tenant_id=tenant.id)),
            "get VLANs with RedBull tenant"
        )

        if not vlans:
            logger.info("No existing VLANs found with RedBull tenant")
            return

        logger.info(f"Found {len(vlans)} VLANs with RedBull tenant - syncing...")

        # OPTIMIZATION: Fetch ALL prefixes with RedBull tenant in ONE API call
        # instead of N calls (one per VLAN). This reduces 100 VLANs from 100 API calls to 1.
        logger.info("Fetching all prefixes for RedBull tenant...")
        all_prefixes = await run_netbox_get(
            lambda: list(nb.ipam.prefixes.filter(tenant_id=tenant.id)),
            "get all prefixes for RedBull tenant"
        )
        logger.info(f"Fetched {len(all_prefixes)} prefixes")

        # Build map: vlan_id → prefix for O(1) lookup
        prefix_by_vlan = {}
        for prefix in all_prefixes:
            if hasattr(prefix, 'vlan') and prefix.vlan:
                vlan_id = prefix.vlan.id if hasattr(prefix.vlan, 'id') else prefix.vlan
                # Store first prefix if multiple (same as before)
                if vlan_id not in prefix_by_vlan:
                    prefix_by_vlan[vlan_id] = prefix

        logger.info(f"Built prefix map for {len(prefix_by_vlan)} VLANs")

        synced_count = 0
        skipped_count = 0
        error_count = 0

        # Now process VLANs using cached data (NO API CALLS in loop)
        from .netbox_cache import get_cached

        for vlan in vlans:
            try:
                # Lookup prefix from map (NO API CALL)
                prefix = prefix_by_vlan.get(vlan.id)

                if not prefix:
                    logger.debug(f"VLAN {vlan.vid} ({vlan.name}) has no associated prefix - skipping")
                    skipped_count += 1
                    continue

                # Extract site from prefix scope using CACHED site groups (NO API CALL)
                site_name = None
                if hasattr(prefix, 'scope_type') and prefix.scope_type and 'sitegroup' in str(prefix.scope_type).lower():
                    if hasattr(prefix, 'scope_id') and prefix.scope_id:
                        # Use cached site groups (pre-fetched at startup)
                        cache_key = f"site_group_{prefix.scope_id}"
                        site_group = get_cached(cache_key)
                        if site_group:
                            site_name = site_group.slug if hasattr(site_group, 'slug') else site_group.get('slug')
                        else:
                            # Fallback: extract from prefix.scope if available
                            if hasattr(prefix, 'scope') and hasattr(prefix.scope, 'slug'):
                                site_name = prefix.scope.slug
                            else:
                                logger.debug(f"Site group {prefix.scope_id} not in cache for VLAN {vlan.vid}")

                if not site_name:
                    logger.debug(f"VLAN {vlan.vid} ({vlan.name}) has no valid site group - skipping")
                    skipped_count += 1
                    continue

                # Extract VRF
                vrf_name = prefix.vrf.name if prefix.vrf else None
                if not vrf_name:
                    logger.debug(f"VLAN {vlan.vid} ({vlan.name}) has no VRF - skipping")
                    skipped_count += 1
                    continue

                # Extract DHCP custom field
                dhcp_enabled = False
                if hasattr(prefix, 'custom_fields') and prefix.custom_fields:
                    dhcp_value = prefix.custom_fields.get('DHCP')
                    dhcp_enabled = dhcp_value is True or str(dhcp_value).lower() == 'true'

                # Extract cluster custom field
                cluster_name = None
                if hasattr(prefix, 'custom_fields') and prefix.custom_fields:
                    cluster_value = prefix.custom_fields.get('Cluster')
                    if cluster_value:
                        cluster_name = str(cluster_value).strip()

                # Log the VLAN being synced
                logger.debug(
                    f"Syncing VLAN {vlan.vid} ({vlan.name}): "
                    f"site={site_name}, vrf={vrf_name}, prefix={prefix.prefix}, "
                    f"dhcp={dhcp_enabled}, cluster={cluster_name or 'unallocated'}"
                )

                synced_count += 1

            except Exception as e:
                logger.error(f"Error syncing VLAN {vlan.vid} ({vlan.name}): {e}", exc_info=True)
                error_count += 1
                continue

        logger.info(
            f"VLAN sync complete: {synced_count} synced, {skipped_count} skipped, {error_count} errors"
        )

    except Exception as e:
        logger.error(f"Error during VLAN sync: {e}", exc_info=True)
        # Don't raise - allow application to start even if sync fails


async def close_storage():
    """Close NetBox storage - cleanup if needed"""
    close_netbox_client()

