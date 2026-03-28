"""Query and search operations for VLAN segments.

Handles filtering, searching, and checking VLAN existence.
"""

import re
import logging
from typing import Optional, List, Dict, Any

from ...database.netbox_segments import get_segments, get_segment_by_id as _get_segment_by_id, get_vrfs as _get_vrfs

logger = logging.getLogger(__name__)


class SegmentQueries:
    """Query and search operations for segments"""

    @staticmethod
    async def get_segments_with_filters(site: Optional[str] = None, allocated: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get segments with optional filters"""
        segments = await get_segments(
            site=site,
            allocated=allocated,
        )

        # Sort by vlan_id
        segments.sort(key=lambda x: x.get("vlan_id", 0))

        return segments

    @staticmethod
    async def check_vlan_exists(site: str, vlan_id: int, vrf: str = None) -> bool:
        """Check if VLAN ID already exists for a (network, site) combination

        Args:
            site: Site name
            vlan_id: VLAN ID
            vrf: VRF/Network name (required for multi-network support)

        Returns:
            True if VLAN exists for this (vrf, site, vlan_id) combination
        """
        kwargs = {"site": site, "vlan_id": vlan_id}
        if vrf:
            kwargs["vrf"] = vrf
        results = await get_segments(**kwargs)
        existing = results[0] if results else None
        return existing is not None

    @staticmethod
    async def check_vlan_exists_excluding_id(site: str, vlan_id: int, exclude_id: str, vrf: str = None) -> bool:
        """Check if VLAN ID already exists for a (network, site) combination, excluding a specific segment ID

        Args:
            site: Site name
            vlan_id: VLAN ID
            exclude_id: Segment ID to exclude from check
            vrf: VRF/Network name (required for multi-network support)

        Returns:
            True if VLAN exists for this (vrf, site, vlan_id) combination (excluding specified ID)
        """
        kwargs = {"site": site, "vlan_id": vlan_id}
        if vrf:
            kwargs["vrf"] = vrf
        results = await get_segments(**kwargs)

        # Exclude the specific segment being updated
        existing = next((s for s in results if str(s.get("_id")) != str(exclude_id)), None)

        if existing:
            logger.debug(f"Found existing VLAN: {existing.get('_id')} (excluding {exclude_id})")
        else:
            logger.debug(f"No conflicting VLAN found")

        logger.debug(f"Checking VLAN existence: vrf={vrf}, site={site}, vlan_id={vlan_id}, exclude_id={exclude_id}")

        return existing is not None

    @staticmethod
    async def search_segments(
        search_query: str,
        site: Optional[str] = None,
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Search segments by cluster name, EPG name, or VLAN ID"""
        # Fetch base set using typed parameters (efficient — uses cache)
        segments = await get_segments(site=site, allocated=allocated)

        # Python-native search across multiple fields
        try:
            vlan_id_search = int(search_query)
        except ValueError:
            vlan_id_search = None

        pattern = re.compile(re.escape(search_query), re.IGNORECASE)

        def _matches_search(s: dict) -> bool:
            if vlan_id_search is not None and s.get("vlan_id") == vlan_id_search:
                return True
            for field in ("cluster_name", "epg_name", "description", "segment"):
                if pattern.search(str(s.get(field) or "")):
                    return True
            return False

        results = [s for s in segments if _matches_search(s)]
        results.sort(key=lambda x: x.get("vlan_id", 0))
        return results

    @staticmethod
    async def get_vrfs() -> List[str]:
        """Get list of available VRFs from NetBox"""
        return await _get_vrfs()
