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

    async def get_or_create_site(self, site_slug: str):
        """Get or create a site group in NetBox (not regular site)"""
        try:
            # Try to get existing site group
            site_group = await run_netbox_get(
                lambda: self.nb.dcim.site_groups.get(slug=site_slug),
                f"get site group {site_slug}"
            )

            if site_group:
                logger.debug(f"Found existing site group: {site_slug}")
                return site_group

            # Create new site group
            logger.info(f"Creating new site group in NetBox: {site_slug}")
            site_group = await run_netbox_write(
                lambda: self.nb.dcim.site_groups.create(
                    name=site_slug.upper(),
                    slug=site_slug
                ),
                f"create site group {site_slug}"
            )
            logger.info(f"Created site group in NetBox: {site_slug}")
            return site_group

        except Exception as e:
            logger.error(f"Error getting/creating site group '{site_slug}': {e}", exc_info=True)
            raise

    async def cleanup_unused_vlan(self, vlan_obj):
        """
        Delete a VLAN from NetBox if it's no longer used by any prefix

        Args:
            vlan_obj: The VLAN object to check and potentially delete
        """
        try:
            # Check if any prefixes are still using this VLAN
            prefixes_using_vlan = await run_netbox_get(
                lambda: list(self.nb.ipam.prefixes.filter(vlan_id=vlan_obj.id)),
                f"check prefixes using VLAN {vlan_obj.vid}"
            )

            if not prefixes_using_vlan or len(prefixes_using_vlan) == 0:
                # No prefixes using this VLAN - safe to delete
                logger.info(f"Deleting unused VLAN {vlan_obj.vid} ({vlan_obj.name}) - ID: {vlan_obj.id}")
                await run_netbox_write(
                    lambda: vlan_obj.delete(),
                    f"delete VLAN {vlan_obj.vid}"
                )
                logger.info(f"Successfully deleted VLAN {vlan_obj.vid}")
            else:
                logger.debug(f"VLAN {vlan_obj.vid} still in use by {len(prefixes_using_vlan)} prefix(es), keeping it")

        except Exception as e:
            logger.warning(f"Error cleaning up VLAN {vlan_obj.vid} ({vlan_obj.name}, ID: {vlan_obj.id}): {e}", exc_info=True)
            # Don't fail the update if cleanup fails

    async def get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None, vrf_name: Optional[str] = None):
        """Get or create a VLAN in NetBox with tenant, role, and group

        IMPORTANT: VLANs should NOT be assigned to site or site_group.
        Only Prefixes are assigned to site_groups.
        """
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

            # Create site group if needed (for Prefix, not VLAN)
            if site_slug:
                await self.get_or_create_site(site_slug)

            # Add tenant "RedBull"
            tenant = await self.get_tenant("RedBull")
            if tenant:
                vlan_data["tenant"] = tenant.id
                logger.debug(f"Assigned tenant 'RedBull' to VLAN")

            # Add role "Data"
            role = await self.get_role("Data", "vlan")
            if role:
                vlan_data["role"] = role.id
                logger.debug(f"Assigned role 'Data' to VLAN")

            # Add VLAN Group if VRF provided
            if vrf_name and site_slug:
                # Extract site number (e.g., "site1" -> "Site1")
                site_group = site_slug.capitalize()
                try:
                    vlan_group = await self.get_or_create_vlan_group(vrf_name, site_group)
                    if vlan_group:
                        vlan_data["group"] = vlan_group.id
                        logger.debug(f"Assigned VLAN group '{vlan_group.name}' to VLAN")
                    else:
                        logger.warning(f"Failed to get/create VLAN group for VRF '{vrf_name}' and site '{site_group}' - VLAN will be created without group")
                except Exception as e:
                    logger.error(f"Error creating VLAN group for VRF '{vrf_name}' and site '{site_group}': {e} - VLAN will be created without group")
                    # Continue VLAN creation even if group creation fails

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
        """Get tenant from NetBox (must exist)"""
        try:
            tenant = await run_netbox_get(
                lambda: self.nb.tenancy.tenants.get(name=tenant_name),
                f"get tenant {tenant_name}"
            )

            if not tenant:
                logger.warning(f"Tenant '{tenant_name}' not found in NetBox")
                return None

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
        """Get role from NetBox (must exist)

        Args:
            role_name: Name of the role (e.g., "Data")
            model_type: Type of model ("vlan" or "prefix")
        """
        try:
            # Roles are in ipam.roles for both VLANs and Prefixes
            role = await run_netbox_get(
                lambda: self.nb.ipam.roles.get(name=role_name),
                f"get role {role_name}"
            )

            if not role:
                logger.warning(f"Role '{role_name}' not found in NetBox")
                return None

            logger.debug(f"Found role in NetBox: {role_name} (ID: {role.id})")
            return role

        except Exception as e:
            logger.error(f"Error fetching role '{role_name}' (model_type: {model_type}) from NetBox: {e}", exc_info=True)
            return None

    async def get_or_create_vlan_group(self, vrf_name: str, site_group: str):
        """Get or create VLAN Group: <VRF_name>-ClickCluster-<Site>
        
        Format: "Network1-ClickCluster-Site1"
        """
        # Format: "<VRF_name>-ClickCluster-<Site>"
        group_name = f"{vrf_name}-ClickCluster-{site_group}"
        logger.debug(f"Getting or creating VLAN Group: {group_name}")

        try:
            # Try to get existing VLAN Group
            vlan_group = await run_netbox_get(
                lambda: self.nb.ipam.vlan_groups.get(name=group_name),
                f"get VLAN group {group_name}"
            )

            if vlan_group:
                logger.debug(f"Found existing VLAN Group: {group_name} (ID: {vlan_group.id})")
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

