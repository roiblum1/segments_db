"""
Segment Search Service
Handles search and retrieval operations for segments
"""
import logging
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from ..utils.database_utils import DatabaseUtils

logger = logging.getLogger(__name__)


class SegmentSearchService:
    """Service for segment search and retrieval operations"""

    @staticmethod
    async def get_segments(
        site: Optional[str] = None,
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Get segments with optional filters

        Args:
            site: Optional site filter
            allocated: Optional allocation status filter

        Returns:
            List of segment dictionaries

        Raises:
            HTTPException: If error occurs during retrieval
        """
        logger.info(f"Getting segments: site={site}, allocated={allocated}")

        try:
            segments = await DatabaseUtils.get_segments_with_filters(site, allocated)
            logger.info(f"Retrieved {len(segments)} segments")
            return segments

        except Exception as e:
            logger.error(f"Error retrieving segments: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def search_segments(
        search_query: str,
        site: Optional[str] = None,
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Search segments by various fields

        Searches across:
        - Cluster name
        - EPG name
        - VLAN ID
        - Description
        - Segment (IP address)

        Args:
            search_query: Search query string
            site: Optional site filter
            allocated: Optional allocation status filter

        Returns:
            List of matching segment dictionaries

        Raises:
            HTTPException: If error occurs during search
        """
        logger.info(
            f"Searching segments: query='{search_query}', "
            f"site={site}, allocated={allocated}"
        )

        try:
            segments = await DatabaseUtils.search_segments(
                search_query,
                site,
                allocated
            )
            logger.debug(f"Found {len(segments)} matching segments")
            return segments

        except Exception as e:
            logger.error(f"Error searching segments: {e}")
            raise HTTPException(status_code=500, detail=str(e))
