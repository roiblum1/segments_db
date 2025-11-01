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
        logger.debug(f"Validating description: '{description[:50]}...'")

        if description and len(description) > 500:
            logger.warning(f"Description too long: {len(description)} characters")
            raise HTTPException(
                status_code=400,
                detail=f"Description too long (max 500 characters, got {len(description)})"
            )

        logger.debug("Description validation passed")

