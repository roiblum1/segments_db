"""Validators module for VLAN Manager.

This module provides a unified Validators class that aggregates all validation methods
from specialized validator modules. This maintains backward compatibility with existing code.

Module structure:
- input_validators.py: Site, VLAN ID, EPG name, cluster name, description
- network_validators.py: IP format, subnet masks, reserved IPs, overlap detection
- security_validators.py: XSS prevention, script injection, path traversal
- organization_validators.py: VRF, allocation state, uniqueness, concurrent modification
- data_validators.py: JSON serialization, timezone, CSV, update data
"""

from .input_validators import InputValidators
from .network_validators import NetworkValidators
from .security_validators import SecurityValidators
from .organization_validators import OrganizationValidators
from .data_validators import DataValidators


class Validators:
    """Unified validators class - aggregates all validation methods for backward compatibility"""

    # Input validation methods
    validate_site = staticmethod(InputValidators.validate_site)
    validate_object_id = staticmethod(InputValidators.validate_object_id)
    validate_epg_name = staticmethod(InputValidators.validate_epg_name)
    validate_vlan_id = staticmethod(InputValidators.validate_vlan_id)
    validate_cluster_name = staticmethod(InputValidators.validate_cluster_name)
    validate_description = staticmethod(InputValidators.validate_description)

    # Network validation methods
    validate_segment_format = staticmethod(NetworkValidators.validate_segment_format)
    validate_subnet_mask = staticmethod(NetworkValidators.validate_subnet_mask)
    validate_no_reserved_ips = staticmethod(NetworkValidators.validate_no_reserved_ips)
    validate_ip_overlap = staticmethod(NetworkValidators.validate_ip_overlap)
    validate_network_broadcast_gateway = staticmethod(NetworkValidators.validate_network_broadcast_gateway)

    # Security validation methods
    sanitize_input = staticmethod(SecurityValidators.sanitize_input)
    validate_no_script_injection = staticmethod(SecurityValidators.validate_no_script_injection)
    validate_no_path_traversal = staticmethod(SecurityValidators.validate_no_path_traversal)
    validate_rate_limit_data = staticmethod(SecurityValidators.validate_rate_limit_data)

    # Organization/business validation methods
    validate_segment_not_allocated = staticmethod(OrganizationValidators.validate_segment_not_allocated)
    validate_vlan_name_uniqueness = staticmethod(OrganizationValidators.validate_vlan_name_uniqueness)
    validate_concurrent_modification = staticmethod(OrganizationValidators.validate_concurrent_modification)
    validate_vrf = staticmethod(OrganizationValidators.validate_vrf)

    # Data validation methods
    validate_update_data = staticmethod(DataValidators.validate_update_data)
    validate_timezone_aware_datetime = staticmethod(DataValidators.validate_timezone_aware_datetime)
    validate_json_serializable = staticmethod(DataValidators.validate_json_serializable)
    validate_csv_row_data = staticmethod(DataValidators.validate_csv_row_data)


# Export all classes for direct import if needed
__all__ = [
    "Validators",
    "InputValidators",
    "NetworkValidators",
    "SecurityValidators",
    "OrganizationValidators",
    "DataValidators",
]
