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
        vrf: str,
        epg_name: str,
        vlan_id: int,
        existing_segments: List[Dict[str, Any]],
        exclude_id: Optional[str] = None
    ) -> None:
        """
        Validate that EPG name + VLAN ID combination is unique per (network, site)

        IMPORTANT: In multi-network environments, the same VLAN ID can exist in:
        - Different networks (VRFs) at the same site  ✓ ALLOWED
        - Different sites in the same network           ✓ ALLOWED
        - Same network and same site                    ✗ NOT ALLOWED

        This prevents confusing situations where same EPG name has different VLAN IDs
        or same VLAN ID has different EPG names within the same (network, site) scope.

        Args:
            site: Site name (e.g., "Site1")
            vrf: VRF/Network name (e.g., "Network1")
            epg_name: EPG name (network endpoint group identifier)
            vlan_id: VLAN ID (1-4094)
            existing_segments: List of existing segments to check against
            exclude_id: Segment ID to exclude from check (for updates)
        """
        for segment in existing_segments:
            # Skip if this is the segment being updated
            if exclude_id and str(segment.get("_id")) == str(exclude_id):
                continue

            # Check same (network, site) combination only
            # Different network = different scope (isolation)
            if segment.get("site") != site or segment.get("vrf") != vrf:
                continue

            # Check if EPG name is same but VLAN ID is different within this (network, site)
            if (segment.get("epg_name") == epg_name and
                segment.get("vlan_id") != vlan_id):
                logger.warning(f"EPG name conflict in {vrf}/{site}: '{epg_name}' already used with VLAN {segment.get('vlan_id')}")
                raise HTTPException(
                    status_code=400,
                    detail=f"EPG name '{epg_name}' is already used with VLAN {segment.get('vlan_id')} "
                           f"in network '{vrf}' at site '{site}'. Cannot assign it to VLAN {vlan_id}."
                )

        logger.debug(f"EPG name uniqueness validation passed for {epg_name} in {vrf}/{site}")

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
        # Import get_storage to use singleton pattern (not NetBoxStorage directly)
        from ...database.netbox_storage import get_storage

        logger.debug(f"Validating VRF: {vrf}")

        if not vrf or not vrf.strip():
            logger.warning("VRF name is empty")
            raise HTTPException(
                status_code=400,
                detail="VRF name cannot be empty"
            )

        # Get available VRFs from NetBox using singleton
        storage = get_storage()
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
