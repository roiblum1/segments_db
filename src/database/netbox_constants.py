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

# Cache TTL values (in seconds)
CACHE_TTL_SHORT = 300      # 5 minutes - VLAN groups (may change with new allocations)
CACHE_TTL_MEDIUM = 600     # 10 minutes - Prefixes, VLANs (change moderately)
CACHE_TTL_LONG = 3600      # 1 hour - Tenants, Roles, Site Groups, VRFs (static data)

