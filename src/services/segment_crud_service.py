"""
Segment CRUD Service
Handles Create, Read, Update, Delete operations for segments
"""
import logging
from typing import Dict, Any
from datetime import datetime, timezone
from fastapi import HTTPException

from ..models.schemas import Segment
from ..utils.database_utils import DatabaseUtils
from .segment_validation_service import SegmentValidationService

logger = logging.getLogger(__name__)


class SegmentCrudService:
    """Service for segment CRUD operations"""

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
    async def get_segment_by_id(segment_id: str) -> Dict[str, Any]:
        """
        Get a single segment by ID

        Args:
            segment_id: Segment ID to retrieve

        Returns:
            Segment data dictionary

        Raises:
            HTTPException: If segment not found or error occurs
        """
        logger.info(f"Getting segment: {segment_id}")

        try:
            # Validate ID format
            SegmentValidationService.validate_object_id(segment_id)

            # Get the segment
            segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")

            # Convert ObjectId to string
            segment["_id"] = str(segment["_id"])

            logger.info(
                f"Retrieved segment {segment_id}: "
                f"site={segment.get('site')}, vlan_id={segment.get('vlan_id')}"
            )
            return segment

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def create_segment(segment: Segment) -> Dict[str, str]:
        """
        Create a new segment

        Args:
            segment: Segment data to create

        Returns:
            Success message with segment ID

        Raises:
            HTTPException: If validation fails or segment already exists
        """
        logger.info(
            f"Creating segment: site={segment.site}, "
            f"vlan_id={segment.vlan_id}, epg={segment.epg_name}"
        )
        logger.debug(f"Full segment data: {segment}")

        try:
            # Get existing segments for validation
            existing_segments = await DatabaseUtils.get_segments_with_filters()

            # Validate segment data
            logger.debug(f"Starting validation for segment {segment.vlan_id}")
            await SegmentValidationService.validate_segment_data(
                segment=segment,
                existing_segments=existing_segments
            )
            logger.debug(f"Validation completed for segment {segment.vlan_id}")

            # Check if VLAN ID already exists for this site
            if await DatabaseUtils.check_vlan_exists(segment.site, segment.vlan_id):
                logger.warning(f"VLAN {segment.vlan_id} already exists for site {segment.site}")
                raise HTTPException(
                    status_code=400,
                    detail=f"VLAN {segment.vlan_id} already exists for site {segment.site}"
                )

            # Create the segment
            segment_data = SegmentCrudService._segment_to_dict(segment)
            segment_id = await DatabaseUtils.create_segment(segment_data)
            logger.info(f"Created segment with ID: {segment_id}")

            return {"message": "Segment created", "id": segment_id}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def update_segment(
        segment_id: str,
        updated_segment: Segment,
        background_tasks=None
    ) -> Dict[str, str]:
        """
        Update an existing segment

        Args:
            segment_id: ID of segment to update
            updated_segment: New segment data
            background_tasks: Optional FastAPI background tasks

        Returns:
            Success message

        Raises:
            HTTPException: If validation fails or segment not found
        """
        logger.info(f"Updating segment: {segment_id}")

        try:
            # Validate ID format
            SegmentValidationService.validate_object_id(segment_id)

            # Check if segment exists
            existing_segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not existing_segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")

            # Get all segments for validation
            all_segments = await DatabaseUtils.get_segments_with_filters()

            # Validate segment data (exclude self from checks)
            await SegmentValidationService.validate_segment_data(
                segment=updated_segment,
                existing_segments=all_segments,
                exclude_id=segment_id
            )

            # Check if VLAN ID change would conflict
            vlan_or_site_changed = (
                existing_segment["vlan_id"] != updated_segment.vlan_id or
                existing_segment["site"] != updated_segment.site
            )

            if vlan_or_site_changed:
                vlan_exists = await DatabaseUtils.check_vlan_exists_excluding_id(
                    site=updated_segment.site,
                    vlan_id=updated_segment.vlan_id,
                    exclude_id=segment_id
                )

                if vlan_exists:
                    logger.warning(
                        f"VLAN {updated_segment.vlan_id} already exists "
                        f"for site {updated_segment.site}"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"VLAN {updated_segment.vlan_id} already exists for site {updated_segment.site}"
                    )

            # Update the segment
            update_data = SegmentCrudService._segment_to_dict(updated_segment)
            success = await DatabaseUtils.update_segment_by_id(segment_id, update_data)

            if not success:
                raise HTTPException(status_code=500, detail="Failed to update segment")

            logger.info(f"Updated segment {segment_id}")
            return {"message": "Segment updated successfully"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    async def update_segment_clusters(segment_id: str, cluster_names: str) -> Dict[str, str]:
        """
        Update cluster assignment for a segment (for shared segments)

        Args:
            segment_id: ID of segment to update
            cluster_names: Comma-separated cluster names

        Returns:
            Success message

        Raises:
            HTTPException: If segment not found or update fails
        """
        logger.info(f"Updating cluster assignment for segment: {segment_id}")

        try:
            # Validate ID format
            SegmentValidationService.validate_object_id(segment_id)

            # Check if segment exists
            existing_segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not existing_segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")

            # Validate and clean cluster names
            validated_cluster_names = SegmentValidationService.validate_cluster_names(
                cluster_names
            )

            # Build update data
            update_data = SegmentCrudService._build_cluster_update_data(
                validated_cluster_names
            )

            # Apply update
            success = await DatabaseUtils.update_segment_by_id(segment_id, update_data)

            if not success:
                raise HTTPException(status_code=500, detail="Failed to update segment clusters")

            logger.info(f"Updated cluster assignment for segment {segment_id}")
            return {"message": "Segment cluster assignment updated successfully"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating segment clusters: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    def _build_cluster_update_data(cluster_names: str) -> Dict[str, Any]:
        """
        Build update data dictionary for cluster assignment

        Args:
            cluster_names: Validated cluster names (or None)

        Returns:
            Dictionary with update fields
        """
        update_data = {}

        if cluster_names:
            # Allocate to clusters
            update_data["cluster_name"] = cluster_names
            update_data["allocated_at"] = datetime.now(timezone.utc)
            update_data["released"] = False
            update_data["released_at"] = None
        else:
            # Release the segment
            update_data["cluster_name"] = None
            update_data["released"] = True
            update_data["released_at"] = datetime.now(timezone.utc)

        return update_data

    @staticmethod
    async def delete_segment(segment_id: str) -> Dict[str, str]:
        """
        Delete a segment

        Args:
            segment_id: ID of segment to delete

        Returns:
            Success message

        Raises:
            HTTPException: If segment not found, allocated, or deletion fails
        """
        logger.info(f"Deleting segment: {segment_id}")

        try:
            # Validate ID format
            SegmentValidationService.validate_object_id(segment_id)

            # Check if segment exists
            segment = await DatabaseUtils.get_segment_by_id(segment_id)
            if not segment:
                logger.warning(f"Segment not found: {segment_id}")
                raise HTTPException(status_code=404, detail="Segment not found")

            # Validate segment can be deleted (not allocated)
            SegmentValidationService.validate_segment_not_allocated(segment)

            # Delete the segment
            success = await DatabaseUtils.delete_segment_by_id(segment_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete segment")

            logger.info(f"Deleted segment {segment_id}")
            return {"message": "Segment deleted"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deleting segment: {e}")
            raise HTTPException(status_code=500, detail=str(e))
