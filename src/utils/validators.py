import logging
from typing import Dict, Any
from fastapi import HTTPException

from ..config.settings import SITES

logger = logging.getLogger(__name__)

class Validators:
    """Validation utilities"""

    @staticmethod
    def validate_site(site: str) -> None:
        """Validate if site is in configured sites"""
        logger.info(f"Validating site: {site}")
        if site not in SITES:
            logger.warning(f"Invalid site requested: {site}, valid sites: {SITES}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid site. Must be one of: {SITES}"
            )
        logger.info(f"Site validation passed: {site}")

    @staticmethod
    def validate_object_id(object_id: str) -> None:
        """Validate ID format (simple validation for string IDs)"""
        logger.info(f"Validating ID: {object_id}")
        if not object_id or not isinstance(object_id, str):
            logger.warning(f"Invalid ID format: {object_id}")
            raise HTTPException(
                status_code=400,
                detail="Invalid ID format"
            )
        logger.info(f"ID validation passed: {object_id}")
    
    @staticmethod
    def validate_segment_not_allocated(segment: Dict[str, Any]) -> None:
        """Validate that segment is not currently allocated"""
        if segment.get("cluster_name") and not segment.get("released", False):
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete allocated segment"
            )
    
    @staticmethod
    def validate_epg_name(epg_name: str) -> None:
        """Validate that EPG name is not empty or whitespace only"""
        logger.info(f"Validating EPG name: '{epg_name}'")
        if not epg_name or not epg_name.strip():
            logger.warning(f"Invalid EPG name: empty or whitespace only")
            raise HTTPException(
                status_code=400,
                detail="EPG name cannot be empty or contain only whitespace"
            )

        # Additional edge cases
        if len(epg_name) > 64:
            logger.warning(f"EPG name too long: {len(epg_name)} characters")
            raise HTTPException(
                status_code=400,
                detail=f"EPG name too long (max 64 characters, got {len(epg_name)})"
            )

        # Check for invalid characters (NetBox VLAN names have restrictions)
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', epg_name):
            logger.warning(f"EPG name contains invalid characters: '{epg_name}'")
            raise HTTPException(
                status_code=400,
                detail="EPG name can only contain letters, numbers, underscores, and hyphens"
            )

        logger.info(f"EPG name validation passed: '{epg_name}'")
    
    @staticmethod
    def validate_segment_format(segment: str, site: str) -> None:
        """Validate that segment IP matches site prefix and is proper network format"""
        import ipaddress
        from ..config.settings import get_site_prefix
        
        logger.info(f"Validating segment format: '{segment}' for site: {site}")
        expected_prefix = get_site_prefix(site)
        
        try:
            # First validate that the segment includes explicit subnet mask
            if '/' not in segment:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid network format. Segment must include subnet mask (e.g., '{segment}/24')"
                )
            
            # Then validate that the segment is in proper network format
            try:
                ipaddress.ip_network(segment, strict=True)
            except ipaddress.AddressValueError:
                # If strict parsing fails, get the correct network address
                network_loose = ipaddress.ip_network(segment, strict=False)
                correct_format = str(network_loose)
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid network format. Use network address '{correct_format}' instead of '{segment}'"
                )
            
            # Parse the network segment for site prefix validation
            network = ipaddress.ip_network(segment, strict=False)
            first_octet = str(network.network_address).split('.')[0]
            
            if first_octet != expected_prefix:
                logger.warning(f"IP prefix mismatch for site '{site}': expected '{expected_prefix}', got '{first_octet}'")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid IP prefix for site '{site}'. Expected to start with '{expected_prefix}', got '{first_octet}'"
                )
            
            logger.info(f"Segment format validation passed: '{segment}' for site {site}")
        except ipaddress.AddressValueError:
            logger.warning(f"Invalid IP network format: {segment}")
            raise HTTPException(status_code=400, detail="Invalid IP network format")

    @staticmethod
    def validate_vlan_id(vlan_id: int) -> None:
        """Validate VLAN ID is within valid range"""
        logger.info(f"Validating VLAN ID: {vlan_id}")

        if not isinstance(vlan_id, int):
            raise HTTPException(
                status_code=400,
                detail=f"VLAN ID must be an integer, got {type(vlan_id).__name__}"
            )

        if vlan_id < 1 or vlan_id > 4094:
            logger.warning(f"VLAN ID out of range: {vlan_id}")
            raise HTTPException(
                status_code=400,
                detail=f"VLAN ID must be between 1 and 4094 (got {vlan_id})"
            )

        # Reserved VLANs
        if vlan_id == 1:
            logger.warning("VLAN 1 is reserved (default VLAN)")

        logger.info(f"VLAN ID validation passed: {vlan_id}")

    @staticmethod
    def validate_cluster_name(cluster_name: str) -> None:
        """Validate cluster name format"""
        logger.info(f"Validating cluster name: '{cluster_name}'")

        if not cluster_name or not cluster_name.strip():
            raise HTTPException(
                status_code=400,
                detail="Cluster name cannot be empty or contain only whitespace"
            )

        if len(cluster_name) > 100:
            logger.warning(f"Cluster name too long: {len(cluster_name)} characters")
            raise HTTPException(
                status_code=400,
                detail=f"Cluster name too long (max 100 characters, got {len(cluster_name)})"
            )

        # Allow letters, numbers, hyphens, underscores, dots (for FQDNs)
        import re
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', cluster_name):
            logger.warning(f"Cluster name contains invalid characters: '{cluster_name}'")
            raise HTTPException(
                status_code=400,
                detail="Cluster name can only contain letters, numbers, hyphens, underscores, and dots"
            )

        logger.info(f"Cluster name validation passed: '{cluster_name}'")

    @staticmethod
    def validate_description(description: str) -> None:
        """Validate description field"""
        if not description:
            # Empty descriptions are allowed
            return

        logger.debug(f"Validating description: '{description[:50]}...'")

        if len(description) > 500:
            logger.warning(f"Description too long: {len(description)} characters")
            raise HTTPException(
                status_code=400,
                detail=f"Description too long (max 500 characters, got {len(description)})"
            )

        # Check for control characters (except newlines and tabs)
        import re
        if re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', description):
            logger.warning("Description contains invalid control characters")
            raise HTTPException(
                status_code=400,
                detail="Description contains invalid control characters"
            )

        logger.debug("Description validation passed")

    @staticmethod
    def validate_subnet_mask(segment: str) -> None:
        """Validate subnet mask is within reasonable range"""
        import ipaddress

        try:
            network = ipaddress.ip_network(segment, strict=False)
            prefix_len = network.prefixlen

            # Typical datacenter subnets: /16 to /29
            # /30 and /31 are too small for practical use (only 2-4 IPs)
            # /32 is a host, not a network
            # /8 to /15 are too large for typical allocations
            if prefix_len < 16 or prefix_len > 29:
                logger.warning(f"Unusual subnet mask: /{prefix_len}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Subnet mask /{prefix_len} is outside typical range (/16 to /29). "
                           f"Use /16-/24 for large networks or /25-/29 for smaller subnets."
                )

            logger.debug(f"Subnet mask validation passed: /{prefix_len}")
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid network format: {str(e)}"
            )

    @staticmethod
    def validate_no_reserved_ips(segment: str) -> None:
        """Validate that segment doesn't use reserved/special IP ranges"""
        import ipaddress

        try:
            network = ipaddress.ip_network(segment, strict=False)

            # Check for reserved ranges
            # 0.0.0.0/8 - Current network
            # 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 - Private (OK for datacenter)
            # 127.0.0.0/8 - Loopback
            # 169.254.0.0/16 - Link-local
            # 224.0.0.0/4 - Multicast
            # 240.0.0.0/4 - Reserved

            first_octet = int(str(network.network_address).split('.')[0])

            # Disallow certain ranges
            if first_octet == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot use 0.0.0.0/8 network (current network identifier)"
                )

            if first_octet == 127:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot use 127.0.0.0/8 network (loopback addresses)"
                )

            if first_octet == 169 and str(network.network_address).startswith("169.254"):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot use 169.254.0.0/16 network (link-local addresses)"
                )

            if first_octet >= 224:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot use {first_octet}.0.0.0/8 network (multicast/reserved range)"
                )

            logger.debug(f"Reserved IP validation passed for {segment}")

        except ipaddress.AddressValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid IP network: {str(e)}"
            )

    @staticmethod
    def sanitize_input(input_str: str, max_length: int = 500) -> str:
        """Sanitize user input to prevent injection attacks"""
        if not input_str:
            return input_str

        # Remove null bytes
        sanitized = input_str.replace('\x00', '')

        # Trim to max length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        # Remove leading/trailing whitespace
        sanitized = sanitized.strip()

        return sanitized

    @staticmethod
    def validate_update_data(update_data: Dict[str, Any]) -> None:
        """Validate bulk update data to ensure no malicious content"""
        import re

        # Check for empty updates
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="Update data cannot be empty"
            )

        # Validate individual fields if present
        if "vlan_id" in update_data:
            Validators.validate_vlan_id(update_data["vlan_id"])

        if "epg_name" in update_data:
            Validators.validate_epg_name(update_data["epg_name"])

        if "cluster_name" in update_data and update_data["cluster_name"]:
            Validators.validate_cluster_name(update_data["cluster_name"])

        if "description" in update_data:
            Validators.validate_description(update_data["description"])

        if "segment" in update_data:
            # Basic format validation (full validation requires site context)
            import ipaddress
            try:
                ipaddress.ip_network(update_data["segment"], strict=False)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid segment format: {update_data['segment']}"
                )

        # Check for suspicious keys that shouldn't be updated directly
        forbidden_keys = ["_id", "id", "created_at", "__proto__", "constructor"]
        for key in update_data.keys():
            if key in forbidden_keys:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update protected field: {key}"
                )

            # Check for potential NoSQL injection patterns in keys
            if "$" in key or "." in key:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid field name: {key}"
                )

        logger.debug("Update data validation passed")

