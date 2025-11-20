"""Constants and configuration values for VLAN Manager.

Centralizes all magic numbers, status values, and configuration constants
used throughout the application.
"""


class CacheTTL:
    """Cache Time-To-Live values in seconds"""
    SHORT = 300      # 5 minutes - for frequently changing data
    MEDIUM = 600     # 10 minutes - for moderately stable data
    LONG = 3600      # 1 hour - for rarely changing data


class NetBoxStatus:
    """NetBox prefix status values"""
    ACTIVE = "active"       # Available for allocation
    RESERVED = "reserved"   # Allocated to a cluster


class NetBoxRole:
    """NetBox role names"""
    DATA = "Data"          # Data role for prefixes and VLANs


class CustomFields:
    """NetBox custom field names"""
    CLUSTER = "Cluster"    # Cluster allocation field
    DHCP = "DHCP"          # DHCP enabled/disabled field


class NetBoxScope:
    """NetBox scope type values"""
    SITE_GROUP = "dcim.sitegroup"  # Site group scope type


class Tenant:
    """Tenant configuration"""
    DEFAULT = "RedBull"    # Default tenant name


class VLANConstraints:
    """VLAN ID constraints"""
    MIN_ID = 1
    MAX_ID = 4094
    RESERVED_DEFAULT = 1   # VLAN 1 is reserved (default VLAN)


class SubnetConstraints:
    """Subnet mask constraints"""
    MIN_PREFIX_LENGTH = 16   # /16 - Largest allowed subnet
    MAX_PREFIX_LENGTH = 29   # /29 - Smallest practical subnet
    MIN_ADDRESSES = 4        # Minimum addresses for a usable network


class FieldLengths:
    """Maximum field lengths"""
    EPG_NAME_MAX = 64
    CLUSTER_NAME_MAX = 100
    DESCRIPTION_MAX = 500
    INPUT_SANITIZE_MAX = 500


class PerformanceThresholds:
    """Performance monitoring thresholds in milliseconds"""
    NETBOX_SLOW_WARNING = 5000      # Warn if NetBox call > 5 seconds
    NETBOX_SEVERE_WARNING = 20000   # Error if NetBox call > 20 seconds
    OPERATION_SLOW = 100            # Warn if operation > 100ms


class ExecutorConfig:
    """Thread pool executor configuration"""
    READ_WORKERS = 30    # Workers for NetBox read operations
    WRITE_WORKERS = 20   # Workers for NetBox write operations


class RateLimits:
    """Rate limiting configuration"""
    DEFAULT_MAX_REQUESTS = 100  # Maximum requests per time window


# Export all constant classes
__all__ = [
    "CacheTTL",
    "NetBoxStatus",
    "NetBoxRole",
    "CustomFields",
    "NetBoxScope",
    "Tenant",
    "VLANConstraints",
    "SubnetConstraints",
    "FieldLengths",
    "PerformanceThresholds",
    "ExecutorConfig",
    "RateLimits",
]
