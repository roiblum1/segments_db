"""Organization and business logic validators for VLAN Manager.

Handles validation of business rules like allocation state, VRF validation,
EPG name uniqueness, and concurrent modification detection.
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class OrganizationValidators:
    """Validators for business logic and organizational rules"""

    @staticmethod
    def validate_segment_not_allocated(segment: Dict[str, Any]) -> None:
        """Validate that segment is not currently allocated"""
        if segment.get("cluster_name") and not segment.get("released", False):
            raise HTTPException(
                status_code=400,
                detail="Cannot delete allocated segment"
            )

    @staticmethod
    def validate_vlan_name_uniqueness(
        site: str,
        epg_name: str,
        vlan_id: int,
        existing_segments: List[Dict[str, Any]],
        exclude_id: Optional[str] = None
    ) -> None:
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

    @staticmethod
    async def validate_vrf(vrf: str) -> None:
        """Validate if VRF exists in NetBox

        Args:
            vrf: VRF name to validate

        Raises:
            HTTPException 400: If VRF is invalid or doesn't exist
        """
        from ...database.netbox_storage import NetBoxStorage

        logger.debug(f"Validating VRF: {vrf}")

        if not vrf or not vrf.strip():
            logger.warning("VRF name is empty")
            raise HTTPException(
                status_code=400,
                detail="VRF name cannot be empty"
            )

        # Get available VRFs from NetBox
        storage = NetBoxStorage()
        try:
            # Get VRFs from storage
            available_vrfs = await storage.get_vrfs()

            if vrf not in available_vrfs:
                logger.warning(f"Invalid VRF: {vrf}, available VRFs: {available_vrfs}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid VRF. Must be one of: {', '.join(available_vrfs)}"
                )

            logger.debug(f"VRF validation passed: {vrf}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error validating VRF: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error validating VRF: {str(e)}"
            )
