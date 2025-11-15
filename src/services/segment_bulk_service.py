"""
Segment Bulk Service
Handles bulk operations for segments
"""
import logging
from typing import List, Dict, Any
from fastapi import HTTPException

from ..models.schemas import Segment
from ..utils.database_utils import DatabaseUtils
from .segment_validation_service import SegmentValidationService

logger = logging.getLogger(__name__)


class SegmentBulkService:
    """Service for bulk segment operations"""

    @staticmethod
    def _segment_to_dict(segment: Segment) -> Dict[str, Any]:
        """Convert Pydantic segment model to dictionary"""
        return {
            "site": segment.site,
            "vlan_id": segment.vlan_id,
            "epg_name": segment.epg_name,
            "segment": segment.segment,
            "dhcp": segment.dhcp,
            "description": segment.description
        }

    @staticmethod
    async def create_segments_bulk(segments: List[Segment]) -> Dict[str, Any]:
        """
        Create multiple segments at once

        Args:
            segments: List of segment data to create

        Returns:
            Dictionary with:
            - message: Summary message
            - created: Number of successfully created segments
            - errors: List of error messages (if any)

        Raises:
            HTTPException: If bulk operation fails entirely
        """
        logger.info(f"Bulk creating {len(segments)} segments")

        try:
            # Get all existing segments once for validation
            existing_segments = await DatabaseUtils.get_segments_with_filters()

            created = 0
            errors = []

            for segment in segments:
                try:
                    # Validate segment data
                    await SegmentValidationService.validate_segment_data(
                        segment=segment,
                        existing_segments=existing_segments
                    )

                    # Check if VLAN ID already exists for this site
                    if await DatabaseUtils.check_vlan_exists(segment.site, segment.vlan_id):
                        error_msg = f"VLAN {segment.vlan_id} already exists for site {segment.site}"
                        logger.warning(error_msg)
                        errors.append(error_msg)
                        continue

                    # Create the segment
                    segment_data = SegmentBulkService._segment_to_dict(segment)
                    await DatabaseUtils.create_segment(segment_data)

                    # Add to existing segments for subsequent validations
                    existing_segments.append(segment_data)

                    created += 1
                    logger.debug(
                        f"Created segment {created}/{len(segments)}: "
                        f"site={segment.site}, vlan_id={segment.vlan_id}"
                    )

                except HTTPException as e:
                    error_msg = f"Site {segment.site}, VLAN {segment.vlan_id}: {e.detail}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

                except Exception as e:
                    error_msg = f"Site {segment.site}, VLAN {segment.vlan_id}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            logger.info(
                f"Bulk creation complete: {created} created, "
                f"{len(errors)} errors"
            )

            return {
                "message": f"Created {created} of {len(segments)} segments",
                "created": created,
                "errors": errors if errors else None
            }

        except Exception as e:
            logger.error(f"Error in bulk creation: {e}")
            raise HTTPException(status_code=500, detail=str(e))
