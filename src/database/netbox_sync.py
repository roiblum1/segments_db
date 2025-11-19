"""
NetBox Sync Functions

This module provides initialization and synchronization functions for NetBox storage.
"""

import logging

from .netbox_client import get_netbox_client, close_netbox_client
from .netbox_cache import invalidate_cache
from .netbox_utils import run_netbox_get

logger = logging.getLogger(__name__)


async def init_storage():
    """Initialize NetBox storage - verify connection and sync existing data"""
    try:
        nb = get_netbox_client()

        # Test connection by getting status
        status = await run_netbox_get(lambda: nb.status(), "get NetBox status")

        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")
        from ..config.settings import NETBOX_URL
        logger.info(f"NetBox URL: {NETBOX_URL}")

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

        synced_count = 0
        skipped_count = 0
        error_count = 0

        for vlan in vlans:
            try:
                # Get associated prefix for this VLAN
                prefixes = await run_netbox_get(
                    lambda v=vlan: list(nb.ipam.prefixes.filter(vlan_id=v.id)),
                    f"get prefixes for VLAN {vlan.vid}"
                )

                if not prefixes:
                    logger.debug(f"VLAN {vlan.vid} ({vlan.name}) has no associated prefix - skipping")
                    skipped_count += 1
                    continue

                prefix = prefixes[0]  # Use first prefix if multiple

                # Extract site from prefix scope
                site_name = None
                if hasattr(prefix, 'scope_type') and prefix.scope_type and 'sitegroup' in str(prefix.scope_type).lower():
                    if hasattr(prefix, 'scope_id') and prefix.scope_id:
                        site_group = await run_netbox_get(
                            lambda: nb.dcim.site_groups.get(prefix.scope_id),
                            f"get site group {prefix.scope_id}"
                        )
                        if site_group:
                            site_name = site_group.slug

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

