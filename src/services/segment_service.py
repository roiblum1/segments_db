"""
DEPRECATED: This file is kept for backward compatibility only.

The SegmentService has been split into focused services:
- SegmentCrudService: Create, Read, Update, Delete operations
- SegmentSearchService: Search and retrieval operations
- SegmentBulkService: Bulk operations
- SegmentValidationService: Validation logic

Please use the new services directly instead of this compatibility layer.
This file will be removed in a future version.
"""
import logging
from typing import Optional, List, Dict, Any

from ..models.schemas import Segment
from .segment_crud_service import SegmentCrudService
from .segment_search_service import SegmentSearchService
from .segment_bulk_service import SegmentBulkService

logger = logging.getLogger(__name__)


class SegmentService:
    """
    DEPRECATED: Compatibility layer for old SegmentService.
    Use the new focused services instead:
    - SegmentCrudService
    - SegmentSearchService
    - SegmentBulkService
    """

    @staticmethod
    async def get_segments(site: Optional[str] = None, allocated: Optional[bool] = None) -> List[Dict[str, Any]]:
        """DEPRECATED: Use SegmentSearchService.get_segments() instead"""
        logger.warning("SegmentService.get_segments() is deprecated. Use SegmentSearchService.get_segments()")
        return await SegmentSearchService.get_segments(site, allocated)

    @staticmethod
    async def search_segments(
        search_query: str,
        site: Optional[str] = None,
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """DEPRECATED: Use SegmentSearchService.search_segments() instead"""
        logger.warning("SegmentService.search_segments() is deprecated. Use SegmentSearchService.search_segments()")
        return await SegmentSearchService.search_segments(search_query, site, allocated)

    @staticmethod
    async def create_segment(segment: Segment) -> Dict[str, str]:
        """DEPRECATED: Use SegmentCrudService.create_segment() instead"""
        logger.warning("SegmentService.create_segment() is deprecated. Use SegmentCrudService.create_segment()")
        return await SegmentCrudService.create_segment(segment)

    @staticmethod
    async def get_segment_by_id(segment_id: str) -> Dict[str, Any]:
        """DEPRECATED: Use SegmentCrudService.get_segment_by_id() instead"""
        logger.warning("SegmentService.get_segment_by_id() is deprecated. Use SegmentCrudService.get_segment_by_id()")
        return await SegmentCrudService.get_segment_by_id(segment_id)

    @staticmethod
    async def update_segment(segment_id: str, updated_segment: Segment, background_tasks=None) -> Dict[str, str]:
        """DEPRECATED: Use SegmentCrudService.update_segment() instead"""
        logger.warning("SegmentService.update_segment() is deprecated. Use SegmentCrudService.update_segment()")
        return await SegmentCrudService.update_segment(segment_id, updated_segment, background_tasks)

    @staticmethod
    async def update_segment_clusters(segment_id: str, cluster_names: str) -> Dict[str, str]:
        """DEPRECATED: Use SegmentCrudService.update_segment_clusters() instead"""
        logger.warning("SegmentService.update_segment_clusters() is deprecated. Use SegmentCrudService.update_segment_clusters()")
        return await SegmentCrudService.update_segment_clusters(segment_id, cluster_names)

    @staticmethod
    async def delete_segment(segment_id: str) -> Dict[str, str]:
        """DEPRECATED: Use SegmentCrudService.delete_segment() instead"""
        logger.warning("SegmentService.delete_segment() is deprecated. Use SegmentCrudService.delete_segment()")
        return await SegmentCrudService.delete_segment(segment_id)

    @staticmethod
    async def create_segments_bulk(segments: List[Segment]) -> Dict[str, Any]:
        """DEPRECATED: Use SegmentBulkService.create_segments_bulk() instead"""
        logger.warning("SegmentService.create_segments_bulk() is deprecated. Use SegmentBulkService.create_segments_bulk()")
        return await SegmentBulkService.create_segments_bulk(segments)
