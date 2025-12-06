"""
NetBox Helper Functions

This module provides helper functions for fetching and managing NetBox objects
(VRF, VLAN, Tenant, Role, Site Group, VLAN Group).
"""

import logging
import re
from typing import Optional, List
from fastapi import HTTPException

from .netbox_client import get_netbox_client
from .netbox_cache import get_cached, set_cache
from .netbox_utils import run_netbox_get, run_netbox_write

logger = logging.getLogger(__name__)


def _sanitize_slug(text: str) -> str:
    """Convert text to a valid NetBox slug (letters, numbers, underscores, hyphens only)
    
    Args:
        text: Input text to convert to slug
        
    Returns:
        Valid slug string
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace spaces and underscores with hyphens
    slug = slug.replace(" ", "-").replace("_", "-")
    # Remove all characters that are not letters, numbers, or hyphens
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    # Replace multiple consecutive hyphens with a single hyphen
    slug = re.sub(r'-+', '-', slug)
    # Remove leading and trailing hyphens
    slug = slug.strip('-')
    return slug


class NetBoxHelpers:
    """Helper class for NetBox object operations"""

    def __init__(self, nb_client):
        """Initialize with NetBox client"""
        self.nb = nb_client

    async def get_site(self, site_slug: str):
        """Get site group from NetBox (must already exist - no creation)

        Production tokens typically don't have permission to create site groups.
        Site groups must be pre-configured in NetBox by administrators.

        Args:
            site_slug: Site group slug to look up

        Returns:
            Site group object from NetBox

        Raises:
            HTTPException: If site group doesn't exist
        """
        try:
            # Get existing site group (NO creation)
            site_group = await run_netbox_get(
                lambda: self.nb.dcim.site_groups.get(slug=site_slug),
                f"get site group {site_slug}"
            )

            if not site_group:
                logger.error(f"Site group '{site_slug}' not found in NetBox")
                raise HTTPException(
                    status_code=400,
                    detail=f"Site group '{site_slug}' does not exist in NetBox. "
                           f"Please create it in NetBox first or contact your administrator."
                )

            logger.debug(f"Found site group: {site_slug} (ID: {site_group.id})")
            return site_group

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting site group '{site_slug}': {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching site group from NetBox: {str(e)}"
            )

    async def cleanup_unused_vlan(self, vlan_obj):
        """
        Delete a VLAN from NetBox if it's no longer used by any prefix

        OPTIMIZED: Uses cached prefix data instead of making API call.
        This reduces 2 API calls per VLAN update to 0-1 calls.

        Args:
            vlan_obj: The VLAN object to check and potentially delete
        """
        try:
            # OPTIMIZATION: Check cached prefixes first (NO API CALL)
            from .netbox_cache import get_cached, invalidate_cache
            cached_prefixes = get_cached("prefixes")

            if cached_prefixes is None:
                # Cache not available - skip cleanup to avoid API spam
                # This is safer than making an API call during VLAN updates
                logger.debug(f"Skipping VLAN {vlan_obj.vid} cleanup - prefix cache unavailable")
                return

            # Check if any cached prefix uses this VLAN (NO API CALL)
            vlan_id_to_check = vlan_obj.id
            in_use = False

            for prefix in cached_prefixes:
                if hasattr(prefix, 'vlan') and prefix.vlan:
                    prefix_vlan_id = prefix.vlan.id if hasattr(prefix.vlan, 'id') else prefix.vlan
                    if prefix_vlan_id == vlan_id_to_check:
                        in_use = True
                        break

            if not in_use:
                # No prefixes using this VLAN - safe to delete (1 API CALL)
                logger.info(f"Deleting unused VLAN {vlan_obj.vid} ({vlan_obj.name}) - ID: {vlan_obj.id}")
                await run_netbox_write(
                    lambda: vlan_obj.delete(),
                    f"delete VLAN {vlan_obj.vid}"
                )
                logger.info(f"Successfully deleted VLAN {vlan_obj.vid}")
                # Invalidate VLAN cache after deletion
                invalidate_cache("vlans")
            else:
                logger.debug(f"VLAN {vlan_obj.vid} still in use, keeping it")

        except Exception as e:
            logger.warning(f"Error cleaning up VLAN {vlan_obj.vid} ({vlan_obj.name}, ID: {vlan_obj.id}): {e}", exc_info=True)
            # Don't fail the update if cleanup fails

    async def get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None, vrf_name: Optional[str] = None):
        """Get or create a VLAN in NetBox with tenant, role, and group

        IMPORTANT: VLANs should NOT be assigned to site or site_group.
        Only Prefixes are assigned to site_groups.

        OPTIMIZED: Parallelizes independent lookups for 4x performance improvement.
        """
        import asyncio

        # Build filter - search by VLAN ID only, not by site
        vlan_filter = {"vid": vlan_id}

        # Try to get existing VLAN
        vlan = await run_netbox_get(
            lambda: self.nb.ipam.vlans.get(**vlan_filter),
            f"get VLAN {vlan_id}"
        )

        if not vlan:
            # Prepare VLAN data - NO site or site_group assignment for VLANs
            vlan_data = {
                "vid": vlan_id,
                "name": name,
                "status": "active",
            }

            # OPTIMIZATION: Parallelize independent lookups (4x faster)
            site_task = self.get_site(site_slug) if site_slug else asyncio.sleep(0)
            tenant_task = self.get_tenant("RedBull")
            role_task = self.get_role("Data", "vlan")

            vlan_group_task = asyncio.sleep(0)
            if vrf_name and site_slug:
                site_group = site_slug.capitalize()
                vlan_group_task = self.get_or_create_vlan_group(vrf_name, site_group)

            # Execute all tasks in parallel
            import time
            t_start = time.time()
            site_obj, tenant, role, vlan_group = await asyncio.gather(
                site_task, tenant_task, role_task, vlan_group_task, return_exceptions=True
            )
            logger.debug(f"⏱️  Parallel VLAN reference lookup took {(time.time() - t_start)*1000:.0f}ms")

            # Add associations (check for exceptions from parallel gather)
            if tenant and not isinstance(tenant, Exception):
                vlan_data["tenant"] = tenant.id
            if role and not isinstance(role, Exception):
                vlan_data["role"] = role.id
            if vlan_group and not isinstance(vlan_group, Exception):
                vlan_data["group"] = vlan_group.id
                logger.debug(f"Assigned VLAN group '{vlan_group.name}' to VLAN")
            elif vrf_name and site_slug:
                logger.warning(f"Failed to get/create VLAN group - VLAN will be created without group")

            # Create new VLAN
            vlan = await run_netbox_write(
                lambda: self.nb.ipam.vlans.create(**vlan_data),
                f"create VLAN {vlan_id}"
            )
            logger.info(f"Created VLAN in NetBox: {vlan_id} ({name}) with tenant=RedBull, role=Data")
        else:
            # VLAN exists - check if name or group needs to be updated
            needs_update = False

            if vlan.name != name:
                logger.info(f"Updating VLAN name from '{vlan.name}' to '{name}' for VLAN ID {vlan_id}")
                vlan.name = name
                needs_update = True

            # Ensure VLAN Group is set if provided and not already set
            if vrf_name and site_slug:
                site_group = site_slug.capitalize()
                expected_group_name = f"{vrf_name}-ClickCluster-{site_group}"

                # Check if VLAN has the correct group
                if not vlan.group or (hasattr(vlan.group, 'name') and vlan.group.name != expected_group_name):
                    try:
                        vlan_group = await self.get_or_create_vlan_group(vrf_name, site_group)
                        if vlan_group:
                            vlan.group = vlan_group.id
                            logger.info(f"Updating VLAN group to '{vlan_group.name}' for VLAN ID {vlan_id}")
                            needs_update = True
                        else:
                            logger.warning(f"Failed to get/create VLAN group '{expected_group_name}' for VLAN {vlan_id}")
                    except Exception as e:
                        logger.error(f"Error creating VLAN group '{expected_group_name}' for VLAN {vlan_id}: {e}")
                        # Continue VLAN update even if group creation fails

            if needs_update:
                await run_netbox_write(
                    lambda: vlan.save(),
                    f"update VLAN {vlan_id}"
                )
                logger.info(f"Updated VLAN {vlan_id} successfully")

        return vlan

    async def get_vrf(self, vrf_name: str):
        """Get VRF from NetBox (do not create - must exist)"""
        try:
            vrf = await run_netbox_get(
                lambda: self.nb.ipam.vrfs.get(name=vrf_name),
                f"get VRF {vrf_name}"
            )

            if not vrf:
                raise HTTPException(
                    status_code=400,
                    detail=f"VRF '{vrf_name}' does not exist in NetBox. Please create it first or select an existing VRF."
                )

            logger.debug(f"Found VRF in NetBox: {vrf_name} (ID: {vrf.id})")
            return vrf

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching VRF '{vrf_name}' from NetBox: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching VRF from NetBox: {str(e)}"
            )

    async def get_tenant(self, tenant_name: str):
        """Get tenant from NetBox (cached for performance)"""
        # Check cache first (pre-fetched at startup)
        cache_key = f"tenant_{tenant_name.lower()}"
        cached_tenant = get_cached(cache_key)
        if cached_tenant is not None:
            logger.debug(f"Using cached tenant: {tenant_name} (ID: {cached_tenant.id})")
            return cached_tenant

        try:
            tenant = await run_netbox_get(
                lambda: self.nb.tenancy.tenants.get(name=tenant_name),
                f"get tenant {tenant_name}"
            )

            if not tenant:
                logger.warning(f"Tenant '{tenant_name}' not found in NetBox")
                return None

            # Cache for future use
            set_cache(cache_key, tenant, ttl=300)
            logger.debug(f"Found tenant in NetBox: {tenant_name} (ID: {tenant.id})")
            return tenant

        except Exception as e:
            logger.error(f"Error fetching tenant '{tenant_name}' from NetBox: {e}", exc_info=True)
            return None

    async def get_redbull_tenant_id(self) -> Optional[int]:
        """Get cached RedBull tenant ID for filtering"""
        cached_id = get_cached("redbull_tenant_id")
        if cached_id is not None:
            return cached_id

        # Fetch tenant ID
        tenant = await self.get_tenant("RedBull")
        if tenant:
            set_cache("redbull_tenant_id", tenant.id)
            return tenant.id

        return None

    async def get_role(self, role_name: str, model_type: str = "vlan"):
        """Get role from NetBox (cached for performance)

        Args:
            role_name: Name of the role (e.g., "Data")
            model_type: Type of model ("vlan" or "prefix")
        """
        # Check cache first (pre-fetched at startup)
        cache_key = f"role_{role_name.lower()}"
        cached_role = get_cached(cache_key)
        if cached_role is not None:
            logger.debug(f"Using cached role: {role_name} (ID: {cached_role.id})")
            return cached_role

        try:
            # Roles are in ipam.roles for both VLANs and Prefixes
            role = await run_netbox_get(
                lambda: self.nb.ipam.roles.get(name=role_name),
                f"get role {role_name}"
            )

            if not role:
                logger.warning(f"Role '{role_name}' not found in NetBox")
                return None

            # Cache for future use
            set_cache(cache_key, role, ttl=300)
            logger.debug(f"Found role in NetBox: {role_name} (ID: {role.id})")
            return role

        except Exception as e:
            logger.error(f"Error fetching role '{role_name}' (model_type: {model_type}) from NetBox: {e}", exc_info=True)
            return None

    async def get_or_create_vlan_group(self, vrf_name: str, site_group: str):
        """Get or create VLAN Group: <VRF_name>-ClickCluster-<Site>

        Format: "Network1-ClickCluster-Site1"

        OPTIMIZED: Caches VLAN groups to avoid repeated lookups.
        """
        # Format: "<VRF_name>-ClickCluster-<Site>"
        group_name = f"{vrf_name}-ClickCluster-{site_group}"
        logger.debug(f"Getting or creating VLAN Group: {group_name}")

        # Check cache first (OPTIMIZATION)
        cache_key = f"vlan_group_{group_name}"
        cached_group = get_cached(cache_key)
        if cached_group:
            logger.debug(f"Using cached VLAN group: {group_name} (ID: {cached_group.id})")
            return cached_group

        try:
            # Try to get existing VLAN Group
            vlan_group = await run_netbox_get(
                lambda: self.nb.ipam.vlan_groups.get(name=group_name),
                f"get VLAN group {group_name}"
            )

            if vlan_group:
                logger.debug(f"Found existing VLAN Group: {group_name} (ID: {vlan_group.id})")
                # Cache for future use
                set_cache(cache_key, vlan_group, ttl=300)
                return vlan_group

            # Create new VLAN Group if it doesn't exist
            logger.info(f"VLAN Group '{group_name}' not found, creating new one...")
            vlan_group_data = {
                "name": group_name,
                "slug": _sanitize_slug(group_name),
            }

            vlan_group = await run_netbox_write(
                lambda: self.nb.ipam.vlan_groups.create(**vlan_group_data),
                f"create VLAN group {group_name}"
            )
            logger.info(f"Successfully created VLAN Group in NetBox: {group_name} (ID: {vlan_group.id})")
            # Cache the newly created group
            set_cache(cache_key, vlan_group, ttl=300)
            return vlan_group

        except Exception as e:
            logger.error(f"Error getting/creating VLAN group '{group_name}': {e}", exc_info=True)
            # Re-raise the exception so callers know the VLAN group creation failed
            raise

    async def get_vrfs(self) -> List[str]:
        """Get list of available VRFs from NetBox (cached for 1 hour)"""
        # Check cache first - VRFs rarely change
        cached_vrfs = get_cached("vrfs")
        if cached_vrfs is not None:
            logger.debug(f"Using cached VRFs: {cached_vrfs}")
            return cached_vrfs

        try:
            vrfs = await run_netbox_get(
                lambda: list(self.nb.ipam.vrfs.all()),
                "fetch VRFs"
            )
            vrf_names = [vrf.name for vrf in vrfs]
            logger.debug(f"Retrieved {len(vrf_names)} VRFs: {vrf_names}")

            # Cache VRFs for 1 hour (they rarely change)
            set_cache("vrfs", vrf_names)

            return vrf_names
        except Exception as e:
            logger.error(f"Error fetching VRFs from NetBox: {e}", exc_info=True)
            raise

