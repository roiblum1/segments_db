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
    
