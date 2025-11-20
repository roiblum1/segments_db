"""
NetBox Data Converters

This module provides conversion functions between NetBox API objects
and our internal data model (segments).
"""

import logging
from typing import Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def prefix_to_segment(prefix, nb_client) -> Dict[str, Any]:
    """Convert NetBox prefix object to our segment format

    Note: In NetBox, the site is associated with the VLAN, not the prefix directly.
    Metadata is extracted from STATUS and DESCRIPTION fields, not comments.
    Comments field is left free for user notes.

    IMPORTANT: This function should NOT make NetBox API calls as it's called
    in loops when converting multiple prefixes. Site groups are now pre-fetched
    at startup and cached.

    Args:
        prefix: NetBox prefix object
        nb_client: NetBox API client (for accessing cached site group data)
    """
    from .netbox_cache import get_cached, set_cache

    # Extract site from Prefix scope (Site Group), not from VLAN
    site_slug = None
    vlan_id = None
    epg_name = ""

    # Extract VLAN ID and EPG name from VLAN object
    if hasattr(prefix, 'vlan') and prefix.vlan:
        # prefix.vlan is already a VLAN Record object in pynetbox
        vlan_obj = prefix.vlan

        # Get VLAN VID (the VLAN number like 100, 101)
        if hasattr(vlan_obj, 'vid'):
            vlan_id = vlan_obj.vid

        # Get EPG name from VLAN name
        if hasattr(vlan_obj, 'name'):
            epg_name = vlan_obj.name

    # Extract site from Prefix scope (Site Group) - NOT from VLAN!
    # VLANs should NOT have site or site_group assignment
    # Only Prefixes should have Site Group scope
    if hasattr(prefix, 'scope_type') and prefix.scope_type and 'sitegroup' in str(prefix.scope_type).lower():
        if hasattr(prefix, 'scope_id') and prefix.scope_id:
            # Use cached site groups (pre-fetched at startup) to avoid API calls
            # This is CRITICAL for performance - never makes blocking API calls
            cache_key = f"site_group_{prefix.scope_id}"
            site_group = get_cached(cache_key)

            if site_group is None:
                # Site group not in cache - this shouldn't happen if pre-fetch worked
                # Log warning but don't fetch (would block and spam NetBox)
                logger.warning(f"Site group {prefix.scope_id} not found in cache for prefix {prefix.id}. "
                             f"Pre-fetch may have failed. Site will be None for this segment.")
                # Fallback: try to extract from prefix object itself if available
                if hasattr(prefix, 'scope') and hasattr(prefix.scope, 'slug'):
                    site_slug = prefix.scope.slug
                    logger.info(f"Extracted site slug '{site_slug}' from prefix.scope object")
            else:
                # Extract slug from cached site group
                if hasattr(site_group, 'slug'):
                    site_slug = site_group.slug
                elif isinstance(site_group, dict) and 'slug' in site_group:
                    site_slug = site_group['slug']
                else:
                    logger.warning(f"Cached site group {prefix.scope_id} has no slug attribute")

    # Extract metadata from STATUS and DESCRIPTION
    status_val = prefix.status.value if hasattr(prefix.status, 'value') else str(prefix.status).lower()
    netbox_description = getattr(prefix, 'description', '') or ""
    user_comments = getattr(prefix, 'comments', '') or ""

    # Determine if allocated or released based on STATUS
    released = (status_val == 'active')

    # Extract cluster name from custom field or description (for backward compatibility)
    cluster_name = None
    custom_fields = getattr(prefix, 'custom_fields', {}) or {}

    if 'Cluster' in custom_fields and custom_fields['Cluster']:
        cluster_name = custom_fields['Cluster']
    elif status_val == 'reserved' and netbox_description.startswith('Cluster: '):
        cluster_name = netbox_description.replace('Cluster: ', '').strip()

    # Extract VRF
    vrf_name = None
    if hasattr(prefix, 'vrf') and prefix.vrf:
        vrf_name = prefix.vrf.name if hasattr(prefix.vrf, 'name') else str(prefix.vrf)

    # Extract DHCP from custom field
    dhcp = False
    if 'DHCP' in custom_fields:
        dhcp = bool(custom_fields['DHCP'])

    # For timestamps, we'll use current time as approximation
    # (NetBox doesn't store these, so we set them when we update)
    allocated_at = None
    released_at = None

    # If it's reserved, set allocated_at to now (approximation)
    if status_val == 'reserved' and cluster_name:
        allocated_at = datetime.now(timezone.utc)

    segment = {
        "_id": str(prefix.id),
        "site": site_slug,
        "vlan_id": vlan_id,
        "epg_name": epg_name,
        "segment": str(prefix.prefix),
        "vrf": vrf_name,
        "dhcp": dhcp,
        "description": user_comments,  # Return user comments as description for API
        "cluster_name": cluster_name,
        "allocated_at": allocated_at,
        "released": released,
        "released_at": released_at,
    }

    return segment

