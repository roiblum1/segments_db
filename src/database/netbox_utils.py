"""
NetBox Utility Functions

Common utilities for safe attribute access, custom fields handling, and validation.
"""

from typing import Any, Optional, Dict
from datetime import datetime, timezone


def safe_get_attr(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get attribute from object, return default if not found"""
    return getattr(obj, attr, default) if obj else default


def safe_get_id(obj: Any) -> Optional[int]:
    """Safely extract ID from NetBox object"""
    if not obj:
        return None
    if hasattr(obj, 'id'):
        return obj.id
    if isinstance(obj, int):
        return obj
    return None


def ensure_custom_fields(obj: Any) -> Dict[str, Any]:
    """Ensure custom_fields dict exists on object"""
    if not hasattr(obj, 'custom_fields') or obj.custom_fields is None:
        obj.custom_fields = {}
    return obj.custom_fields


def get_custom_field(obj: Any, field_name: str, default: Any = None) -> Any:
    """Get custom field value safely"""
    custom_fields = getattr(obj, 'custom_fields', {}) or {}
    return custom_fields.get(field_name, default)


def set_custom_field(obj: Any, field_name: str, value: Any) -> None:
    """Set custom field value safely"""
    ensure_custom_fields(obj)
    obj.custom_fields[field_name] = value


def get_site_slug_from_prefix(prefix: Any) -> Optional[str]:
    """Extract site slug from prefix scope (Site Group)"""
    if not hasattr(prefix, 'scope_type') or not prefix.scope_type:
        return None
    
    if 'sitegroup' not in str(prefix.scope_type).lower():
        return None
    
    if not hasattr(prefix, 'scope_id') or not prefix.scope_id:
        return None
    
    # Try to get from cached site group
    from .netbox_cache import get_cached
    cache_key = f"site_group_{prefix.scope_id}"
    site_group = get_cached(cache_key)
    
    if site_group:
        if hasattr(site_group, 'slug'):
            return site_group.slug
        if isinstance(site_group, dict) and 'slug' in site_group:
            return site_group['slug']
    
    # Fallback to prefix.scope if available
    if hasattr(prefix, 'scope') and hasattr(prefix.scope, 'slug'):
        return prefix.scope.slug
    
    return None


def get_vlan_info(vlan_obj: Any) -> tuple[Optional[int], str]:
    """Extract VLAN ID and name from VLAN object"""
    if not vlan_obj:
        return None, ""
    
    vlan_id = safe_get_attr(vlan_obj, 'vid')
    vlan_name = safe_get_attr(vlan_obj, 'name', "")
    return vlan_id, vlan_name


def prefix_to_segment(prefix, nb_client) -> Dict[str, Any]:
    """Convert NetBox prefix object to our segment format"""
    from .netbox_constants import (
        CUSTOM_FIELD_CLUSTER, CUSTOM_FIELD_DHCP, STATUS_ACTIVE, STATUS_RESERVED,
        DESCRIPTION_CLUSTER_PREFIX
    )
    
    # Extract VLAN info
    vlan_obj = safe_get_attr(prefix, 'vlan')
    vlan_id, epg_name = get_vlan_info(vlan_obj) if vlan_obj else (None, "")

    # Extract site from Prefix scope (Site Group)
    site_slug = get_site_slug_from_prefix(prefix)

    # Extract metadata
    status_val = safe_get_attr(prefix.status, 'value') or str(prefix.status).lower()
    user_comments = safe_get_attr(prefix, 'comments', "") or ""

    # Extract cluster name from custom field
    cluster_name = get_custom_field(prefix, CUSTOM_FIELD_CLUSTER)
    if not cluster_name and status_val == STATUS_RESERVED:
        description = safe_get_attr(prefix, 'description', '')
        if description.startswith(DESCRIPTION_CLUSTER_PREFIX):
            cluster_name = description.replace(DESCRIPTION_CLUSTER_PREFIX, '').strip()

    # Determine released status:
    # - status="active" + cluster_name=None → released=False (never allocated, available)
    # - status="reserved" + cluster_name=None → released=True (previously allocated, now released)
    # - status="reserved" + cluster_name!=None → released=False (currently allocated)
    if status_val == STATUS_ACTIVE:
        released = False  # Never allocated
    elif status_val == STATUS_RESERVED:
        released = (cluster_name is None)  # Released if no cluster assigned
    else:
        released = False  # Default to not released

    # Extract VRF
    vrf_obj = safe_get_attr(prefix, 'vrf')
    vrf_name = safe_get_attr(vrf_obj, 'name') if vrf_obj else None

    # Extract DHCP from custom field
    dhcp = bool(get_custom_field(prefix, CUSTOM_FIELD_DHCP, False))

    # Timestamps
    allocated_at = datetime.now(timezone.utc) if (status_val == STATUS_RESERVED and cluster_name) else None

    return {
        "_id": str(prefix.id),
        "site": site_slug,
        "vlan_id": vlan_id,
        "epg_name": epg_name,
        "segment": str(prefix.prefix),
        "vrf": vrf_name,
        "dhcp": dhcp,
        "description": user_comments,
        "cluster_name": cluster_name,
        "allocated_at": allocated_at,
        "released": released,
        "released_at": None,
    }

