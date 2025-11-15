import logging
import re
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

    @staticmethod
    def validate_ip_overlap(new_segment: str, existing_segments: list) -> None:
        """
        Validate that a new segment doesn't overlap with existing segments

        Args:
            new_segment: New IP network to validate (e.g., "192.168.1.0/24")
            existing_segments: List of existing segment dictionaries with 'segment' field

        Raises:
            HTTPException: If overlap detected
        """
        import ipaddress

        try:
            new_network = ipaddress.ip_network(new_segment, strict=False)

            for existing in existing_segments:
                if not existing.get("segment"):
                    continue

                try:
                    existing_network = ipaddress.ip_network(existing["segment"], strict=False)

                    # Check if networks overlap
                    if new_network.overlaps(existing_network):
                        logger.warning(f"IP overlap detected: {new_segment} overlaps with {existing['segment']}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"IP segment {new_segment} overlaps with existing segment {existing['segment']} "
                                   f"(Site: {existing.get('site')}, VLAN: {existing.get('vlan_id')})"
                        )

                except ValueError as e:
                    # Skip invalid existing segments
                    logger.warning(f"Skipping invalid existing segment: {existing.get('segment')}")
                    continue

            logger.debug(f"No IP overlap detected for {new_segment}")

        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid IP network format: {str(e)}"
            )

    @staticmethod
    def validate_network_broadcast_gateway(segment: str) -> None:
        """
        Validate network has sufficient usable IPs (not just network and broadcast)

        A /31 network has only 2 IPs (both usable in point-to-point)
        A /30 network has 4 IPs (2 usable, 2 for network/broadcast)
        Warn about very small networks
        """
        import ipaddress

        try:
            network = ipaddress.ip_network(segment, strict=False)
            num_addresses = network.num_addresses

            # For networks with less than 4 addresses, warn user
            if num_addresses < 4:
                logger.warning(f"Very small network: {segment} has only {num_addresses} addresses")
                raise HTTPException(
                    status_code=400,
                    detail=f"Network {segment} is too small ({num_addresses} addresses). "
                           f"Minimum recommended size is /30 (4 addresses) for non-point-to-point links."
                )

            # For /24 and larger, verify reasonable size
            usable_hosts = num_addresses - 2  # Exclude network and broadcast

            if usable_hosts < 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Network {segment} has no usable host addresses"
                )

            logger.debug(f"Network validation passed: {segment} has {usable_hosts} usable addresses")

        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid network format: {str(e)}"
            )

    @staticmethod
    def validate_vlan_name_uniqueness(site: str, epg_name: str, vlan_id: int, existing_segments: list, exclude_id: str = None) -> None:
        """
        Validate that EPG name + VLAN ID combination is unique per site

        This prevents confusing situations where same EPG name has different VLAN IDs
        or same VLAN ID has different EPG names at the same site
        """
        for segment in existing_segments:
            # Skip if this is the segment being updated
            if exclude_id and str(segment.get("_id")) == str(exclude_id):
                continue

            # Check same site only
            if segment.get("site") != site:
                continue

            # Check if EPG name is same but VLAN ID is different
            if (segment.get("epg_name") == epg_name and
                segment.get("vlan_id") != vlan_id):
                logger.warning(f"EPG name conflict: '{epg_name}' already used with VLAN {segment.get('vlan_id')} at {site}")
                raise HTTPException(
                    status_code=400,
                    detail=f"EPG name '{epg_name}' is already used with VLAN {segment.get('vlan_id')} at site {site}. "
                           f"Cannot assign it to VLAN {vlan_id}."
                )

        logger.debug(f"EPG name uniqueness validation passed for {epg_name} at {site}")

    @staticmethod
    def validate_timezone_aware_datetime(dt_value: Any) -> None:
        """Validate that datetime is timezone-aware to prevent timezone bugs"""
        from datetime import datetime

        if dt_value is None:
            return

        if not isinstance(dt_value, datetime):
            raise HTTPException(
                status_code=400,
                detail=f"Expected datetime object, got {type(dt_value).__name__}"
            )

        if dt_value.tzinfo is None:
            raise HTTPException(
                status_code=400,
                detail="Datetime must be timezone-aware. Use datetime.now(timezone.utc)"
            )

        logger.debug("Datetime timezone validation passed")

    @staticmethod
    def validate_json_serializable(data: Any, field_name: str = "data") -> None:
        """
        Validate that data can be JSON serialized
        Prevents issues with datetime, bytes, custom objects
        """
        import json

        # Check for types that aren't natively JSON serializable
        # and shouldn't be converted to strings
        if hasattr(data, '__dict__') and not isinstance(data, (dict, list, str, int, float, bool, type(None))):
            logger.error(f"JSON serialization failed for {field_name}: custom object {type(data)}")
            raise HTTPException(
                status_code=400,
                detail=f"Field '{field_name}' contains non-serializable custom object: {type(data).__name__}"
            )

        try:
            # Try to serialize without default handler first (strict check)
            json.dumps(data)
        except (TypeError, ValueError) as e:
            # Check if it's a datetime (acceptable with default handler)
            from datetime import datetime, date
            if isinstance(data, (datetime, date)):
                # Datetime is acceptable - can be serialized with default=str
                pass
            else:
                logger.error(f"JSON serialization failed for {field_name}: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field_name}' contains non-serializable data: {str(e)}"
                )

        logger.debug(f"JSON serialization validation passed for {field_name}")

    @staticmethod
    def validate_no_script_injection(text: str, field_name: str = "field") -> None:
        """
        Validate that text doesn't contain script injection patterns
        Protects against XSS when data is displayed in web UI
        """
        if not text:
            return

        # Check for common script injection patterns
        dangerous_patterns = [
            r'<script',
            r'javascript:',
            r'onerror=',
            r'onload=',
            r'onclick=',
            r'<iframe',
            r'<embed',
            r'<object',
            r'eval\(',
            r'expression\(',
        ]

        text_lower = text.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, text_lower):
                logger.warning(f"Potential script injection detected in {field_name}: {pattern}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field_name}' contains potentially dangerous content: {pattern}"
                )

        logger.debug(f"Script injection validation passed for {field_name}")

    @staticmethod
    def validate_rate_limit_data(request_count: int, time_window_seconds: int, max_requests: int = 100) -> None:
        """
        Helper to validate rate limiting (not enforcing, just validating params)
        Actual rate limiting should be done at API gateway level
        """
        if request_count < 0:
            raise HTTPException(status_code=400, detail="Request count cannot be negative")

        if time_window_seconds <= 0:
            raise HTTPException(status_code=400, detail="Time window must be positive")

        if request_count > max_requests:
            logger.warning(f"Rate limit exceeded: {request_count} requests in {time_window_seconds}s")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {request_count} requests in {time_window_seconds} seconds. Maximum: {max_requests}"
            )

    @staticmethod
    def validate_no_path_traversal(filename: str) -> None:
        """
        Validate filename doesn't contain path traversal attempts
        Prevents accessing files outside intended directory
        """
        if not filename:
            return

        # Check for path traversal patterns
        dangerous_patterns = [
            '..',      # Parent directory
            '~',       # Home directory
            '/',       # Absolute path (at start)
            '\\',      # Windows path separator
        ]

        for pattern in dangerous_patterns:
            if pattern in filename:
                logger.warning(f"Path traversal attempt detected in filename: {filename}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid filename: contains dangerous pattern '{pattern}'"
                )

        # Additional checks
        if filename.startswith('/') or filename.startswith('\\'):
            raise HTTPException(
                status_code=400,
                detail="Filename cannot be an absolute path"
            )

        logger.debug(f"Path traversal validation passed for: {filename}")

    @staticmethod
    def validate_csv_row_data(row_data: dict, row_number: int) -> None:
        """
        Validate CSV import row data

        Args:
            row_data: Dictionary of row data
            row_number: Row number for error reporting
        """
        required_fields = ['site', 'vlan_id', 'epg_name', 'segment']

        # Check required fields
        missing_fields = [field for field in required_fields if not row_data.get(field)]
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Row {row_number}: Missing required fields: {', '.join(missing_fields)}"
            )

        # Validate vlan_id is numeric
        try:
            vlan_id = int(row_data['vlan_id'])
            Validators.validate_vlan_id(vlan_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail=f"Row {row_number}: Invalid VLAN ID '{row_data.get('vlan_id')}' - must be integer between 1-4094"
            )

        # Validate other fields
        Validators.validate_epg_name(row_data['epg_name'])
        Validators.validate_site(row_data['site'])

        # Validate description if present
        if row_data.get('description'):
            Validators.validate_description(row_data['description'])

        logger.debug(f"CSV row {row_number} validation passed")

    @staticmethod
    def validate_concurrent_modification(original_updated_at: Any, current_updated_at: Any) -> None:
        """
        Validate optimistic locking - ensure record hasn't been modified since read

        Args:
            original_updated_at: Timestamp when record was read
            current_updated_at: Current timestamp in database

        Raises:
            HTTPException 409: If record was modified by another request
        """
        if original_updated_at != current_updated_at:
            logger.warning("Concurrent modification detected")
            raise HTTPException(
                status_code=409,
                detail="Record was modified by another request. Please refresh and try again."
            )


