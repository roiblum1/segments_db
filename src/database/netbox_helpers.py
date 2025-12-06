"""
NetBox Helper Functions

This module provides helper functions for fetching and managing NetBox objects
(VRF, VLAN, Tenant, Role, Site Group, VLAN Group).
"""

import logging
import re
from typing import Optional, List
from fastapi import HTTPException

from .netbox_client import get_netbox_client, run_netbox_get, run_netbox_write
from .netbox_cache import get_cached, set_cache
from .netbox_utils import safe_get_id, safe_get_attr
from .netbox_constants import (
    TENANT_REDBULL, ROLE_DATA, STATUS_ACTIVE, VLAN_GROUP_PREFIX,
    CACHE_KEY_REDBULL_TENANT_ID, CACHE_KEY_PREFIXES, CACHE_KEY_VLANS,
    get_tenant_cache_key, get_role_cache_key,
    format_vlan_group_name, get_vlan_group_cache_key
)

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
        """Get site group from NetBox (must already exist - no creation)"""
        normalized_slug = site_slug.lower()
        site_group = await run_netbox_get(
            lambda: self.nb.dcim.site_groups.get(slug=normalized_slug),
            f"get site group {normalized_slug}"
        )

        if not site_group:
            raise HTTPException(
                status_code=400,
                detail=f"Site group '{site_slug}' does not exist in NetBox. "
                       f"Please create it in NetBox first or contact your administrator."
            )

        return site_group

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
            cached_prefixes = get_cached(CACHE_KEY_PREFIXES)

            if cached_prefixes is None:
                # Cache not available - skip cleanup to avoid API spam
                # This is safer than making an API call during VLAN updates
                return

            # Check if any cached prefix uses this VLAN (NO API CALL)
            vlan_id_to_check = safe_get_id(vlan_obj)
            in_use = any(
                safe_get_id(safe_get_attr(prefix, 'vlan')) == vlan_id_to_check
                for prefix in cached_prefixes
            )

            if not in_use:
                # No prefixes using this VLAN - safe to delete (1 API CALL)
                await run_netbox_write(
                    lambda: vlan_obj.delete(),
                    f"delete VLAN {vlan_obj.vid}"
                )
                # Invalidate VLAN cache after deletion
                invalidate_cache(CACHE_KEY_VLANS)

        except Exception as e:
            logger.warning(f"Error cleaning up VLAN {vlan_obj.vid} ({vlan_obj.name}, ID: {vlan_obj.id}): {e}", exc_info=True)
            # Don't fail the update if cleanup fails

    async def get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None, vrf_name: Optional[str] = None):
        """Get or create a VLAN in NetBox with tenant, role, and group

        IMPORTANT: VLANs should NOT be assigned to site or site_group.
        Only Prefixes are assigned to site_groups.

        IMPORTANT: NetBox has uniqueness constraint: VLANs must be unique by (Group, Name).
        However, our business logic is: VLANs are unique by (Network, Site, VLAN_ID).
        
        This means:
        - VLAN 22 can exist in Network1/Site1 AND Network2/Site1 (different groups) ✓
        - VLAN 22 can exist in Network1/Site1 AND Network1/Site2 (different groups) ✓
        - VLAN 22 CANNOT exist twice in Network1/Site1 (same group) ✗
        
        When updating a VLAN's group, if another VLAN already has that group+name,
        we should use the existing VLAN instead of creating a duplicate.
        """
        # Build filter - search by VLAN ID only, not by site
        vlan_filter = {"vid": vlan_id}

        # Try to get existing VLAN by VID
        vlan = await run_netbox_get(
            lambda: self.nb.ipam.vlans.get(**vlan_filter),
            f"get VLAN {vlan_id}"
        )

        if not vlan:
            # Prepare VLAN data - NO site or site_group assignment for VLANs
            vlan_data = {
                "vid": vlan_id,
                "name": name,
            }

            # Fetch reference data sequentially (all cached lookups)
            # Tenant and Role are cached (3600s TTL) - lookups are instant
            tenant = await self.get_tenant(TENANT_REDBULL)
            if tenant:
                vlan_data["tenant"] = tenant.id

            role = await self.get_role(ROLE_DATA, "vlan")
            if role:
                vlan_data["role"] = role.id

            # VLAN Group (may need creation)
            if vrf_name and site_slug:
                # Normalize site_slug to match NetBox site group naming (capitalized)
                site_group = site_slug.capitalize()
                try:
                    vlan_group = await self.get_or_create_vlan_group(vrf_name, site_group)
                    if vlan_group:
                        vlan_data["group"] = vlan_group.id
                except Exception as e:
                    logger.warning(f"Failed to get/create VLAN group: {e}")

            # Create new VLAN
            vlan_data["status"] = STATUS_ACTIVE
            vlan = await run_netbox_write(
                lambda: self.nb.ipam.vlans.create(**vlan_data),
                f"create VLAN {vlan_id}"
            )
        else:
            # VLAN exists - check if we need to update group
            if vrf_name and site_slug:
                site_group = site_slug.capitalize()
                vlan_group = await self.get_or_create_vlan_group(vrf_name, site_group)
                
                # Check if VLAN with same VID already exists in target group
                existing_vlan = await run_netbox_get(
                    lambda: self.nb.ipam.vlans.get(group_id=vlan_group.id, vid=vlan_id),
                    f"check VLAN {vlan_id} in group '{vlan_group.name}'"
                )
                
                if existing_vlan:
                    # Use existing VLAN, update name if needed
                    if existing_vlan.name != name:
                        existing_vlan.name = name
                        await run_netbox_write(lambda: existing_vlan.save(), f"update VLAN {vlan_id} name")
                    return existing_vlan
                
                # Update current VLAN's group
                if not vlan.group or (hasattr(vlan.group, 'id') and vlan.group.id != vlan_group.id):
                    vlan.group = vlan_group.id
                    if vlan.name != name:
                        vlan.name = name
                    await run_netbox_write(lambda: vlan.save(), f"update VLAN {vlan_id}")
            elif vlan.name != name:
                # Only name update needed
                vlan.name = name
                await run_netbox_write(lambda: vlan.save(), f"update VLAN {vlan_id} name")

        return vlan

    async def get_vrf(self, vrf_name: str):
        """Get VRF from NetBox (do not create - must exist)"""
        vrf = await run_netbox_get(
            lambda: self.nb.ipam.vrfs.get(name=vrf_name),
            f"get VRF {vrf_name}"
        )

        if not vrf:
            raise HTTPException(
                status_code=400,
                detail=f"VRF '{vrf_name}' does not exist in NetBox. Please create it first or select an existing VRF."
            )

        return vrf

    async def get_tenant(self, tenant_name: str):
        """Get tenant from NetBox (cached for performance)"""
        # Check cache first (pre-fetched at startup)
        cache_key = get_tenant_cache_key(tenant_name)
        cached_tenant = get_cached(cache_key)
        if cached_tenant is not None:
            return cached_tenant

        try:
            tenant = await run_netbox_get(
                lambda: self.nb.tenancy.tenants.get(name=tenant_name),
                f"get tenant {tenant_name}"
            )

            if not tenant:
                logger.warning(f"Tenant '{tenant_name}' not found in NetBox")
                return None

            # Cache for future use (static data - 1 hour TTL)
            set_cache(cache_key, tenant, ttl=3600)
            return tenant

        except Exception as e:
            logger.error(f"Error fetching tenant '{tenant_name}' from NetBox: {e}", exc_info=True)
            return None

    async def get_redbull_tenant_id(self) -> Optional[int]:
        """Get cached RedBull tenant ID for filtering"""
        cached_id = get_cached(CACHE_KEY_REDBULL_TENANT_ID)
        if cached_id is not None:
            return cached_id

        # Fetch tenant ID
        tenant = await self.get_tenant(TENANT_REDBULL)
        if tenant:
            set_cache(CACHE_KEY_REDBULL_TENANT_ID, tenant.id)
            return tenant.id

        return None

    async def get_role(self, role_name: str, model_type: str = "vlan"):
        """Get role from NetBox (cached for performance)

        Args:
            role_name: Name of the role (e.g., "Data")
            model_type: Type of model ("vlan" or "prefix")
        """
        # Check cache first (pre-fetched at startup)
        cache_key = get_role_cache_key(role_name)
        cached_role = get_cached(cache_key)
        if cached_role is not None:
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

            # Cache for future use (static data - 1 hour TTL)
            set_cache(cache_key, role, ttl=3600)
            return role

        except Exception as e:
            logger.error(f"Error fetching role '{role_name}' (model_type: {model_type}) from NetBox: {e}", exc_info=True)
            return None

    async def get_or_create_vlan_group(self, vrf_name: str, site_group: str):
        """Get or create VLAN Group: <VRF_name>-ClickCluster-<Site>

        Format: "Network1-ClickCluster-Site1"

        OPTIMIZED: Caches VLAN groups to avoid repeated lookups.
        """
        group_name = format_vlan_group_name(vrf_name, site_group)

        # Check cache first (OPTIMIZATION)
        cache_key = get_vlan_group_cache_key(group_name)
        cached_group = get_cached(cache_key)
        if cached_group:
            return cached_group

        try:
            # Try to get existing VLAN Group
            vlan_group = await run_netbox_get(
                lambda: self.nb.ipam.vlan_groups.get(name=group_name),
                f"get VLAN group {group_name}"
            )

            if vlan_group:
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
            return cached_vrfs

        try:
            vrfs = await run_netbox_get(
                lambda: list(self.nb.ipam.vrfs.all()),
                "fetch VRFs"
            )
            vrf_names = [vrf.name for vrf in vrfs]

            # Cache VRFs for 1 hour (they rarely change)
            set_cache("vrfs", vrf_names)

            return vrf_names
        except Exception as e:
            logger.error(f"Error fetching VRFs from NetBox: {e}", exc_info=True)
            raise

