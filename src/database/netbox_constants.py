"""
NetBox Constants

Centralized constants to avoid magic strings throughout the codebase.
"""

# Tenant names
TENANT_REDBULL = "RedBull"
TENANT_REDBULL_SLUG = "redbull"

# Role names
ROLE_DATA = "Data"

# Custom field names
CUSTOM_FIELD_DHCP = "DHCP"
CUSTOM_FIELD_CLUSTER = "Cluster"

# Status values
STATUS_ACTIVE = "active"
STATUS_RESERVED = "reserved"

# Scope types
SCOPE_TYPE_SITEGROUP = "dcim.sitegroup"

# VLAN Group naming
VLAN_GROUP_PREFIX = "ClickCluster"

# Description prefixes (for backward compatibility)
DESCRIPTION_CLUSTER_PREFIX = "Cluster: "

# Cache keys
CACHE_KEY_REDBULL_TENANT_ID = "redbull_tenant_id"
CACHE_KEY_TENANT_REDBULL = "tenant_redbull"
CACHE_KEY_PREFIXES = "prefixes"
CACHE_KEY_VLANS = "vlans"
CACHE_KEY_VRFS = "vrfs"

def get_tenant_cache_key(tenant_name: str) -> str:
    """Get cache key for tenant"""
    return f"tenant_{tenant_name.lower()}"

def get_role_cache_key(role_name: str) -> str:
    """Get cache key for role"""
    return f"role_{role_name.lower()}"

def get_site_group_cache_key(site_group_id: int) -> str:
    """Get cache key for site group"""
    return f"site_group_{site_group_id}"

def get_vlan_group_cache_key(group_name: str) -> str:
    """Get cache key for VLAN group"""
    return f"vlan_group_{group_name}"

def format_vlan_group_name(vrf_name: str, site_group: str) -> str:
    """Format VLAN group name: <VRF_name>-ClickCluster-<Site>"""
    return f"{vrf_name}-{VLAN_GROUP_PREFIX}-{site_group}"

