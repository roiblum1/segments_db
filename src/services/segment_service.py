import logging
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from ..models.schemas import Segment
from ..utils.database_utils import DatabaseUtils
from ..utils.validators import Validators
from ..utils.error_handlers import handle_netbox_errors, retry_on_network_error
from ..utils.logging_decorators import log_operation_timing

logger = logging.getLogger(__name__)

class SegmentService:
    """Service class for segment management operations"""
    
    @staticmethod
    async def _validate_segment_data(segment: Segment, exclude_id: str = None) -> None:
        """Common validation for segment data"""
        # Basic field validation
        Validators.validate_site(segment.site)
        await Validators.validate_vrf(segment.vrf)  # VRF validation (async)
        Validators.validate_epg_name(segment.epg_name)
        Validators.validate_vlan_id(segment.vlan_id)

        # Network validation (with network-specific site prefix)
        Validators.validate_segment_format(segment.segment, segment.site, segment.vrf)
        Validators.validate_subnet_mask(segment.segment)
        Validators.validate_no_reserved_ips(segment.segment)
        Validators.validate_network_broadcast_gateway(segment.segment)

        # Description validation (XSS protection)
        if segment.description:
            Validators.validate_description(segment.description)
            Validators.validate_no_script_injection(segment.description, "description")

        # EPG name XSS protection
        Validators.validate_no_script_injection(segment.epg_name, "epg_name")

        # IP overlap validation - get all existing segments
        existing_segments = await DatabaseUtils.get_segments_with_filters()
        if exclude_id:
            # Exclude the segment being updated
            existing_segments = [s for s in existing_segments if str(s.get("_id")) != str(exclude_id)]

        Validators.validate_ip_overlap(segment.segment, existing_segments)

        # EPG name uniqueness validation (scoped to network+site)
        Validators.validate_vlan_name_uniqueness(
            site=segment.site,
            vrf=segment.vrf,
            epg_name=segment.epg_name,
            vlan_id=segment.vlan_id,
            existing_segments=existing_segments,
            exclude_id=exclude_id
        )
    
    @staticmethod
    def _segment_to_dict(segment: Segment) -> Dict[str, Any]:
        """Convert segment object to dictionary"""
        return {
            "site": segment.site,
            "vlan_id": segment.vlan_id,
            "epg_name": segment.epg_name,
            "segment": segment.segment,
            "vrf": segment.vrf,
            "dhcp": segment.dhcp,
            "description": segment.description
        }
    
    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("get_segments", threshold_ms=1000)
    async def get_segments(site: Optional[str] = None, allocated: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Get segments with optional filters"""
        segments = await DatabaseUtils.get_segments_with_filters(site, allocated)
        logger.debug(f"Retrieved {len(segments)} segments")
        return segments
    
    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("search_segments", threshold_ms=1000)
    async def search_segments(
        search_query: str,
        site: Optional[str] = None,
        allocated: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Search segments by cluster name, EPG name, VLAN ID, description, or segment"""
        segments = await DatabaseUtils.search_segments(search_query, site, allocated)
        logger.debug(f"Found {len(segments)} matching segments for query '{search_query}'")
        return segments
    
    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("create_segment", threshold_ms=2000)
    async def create_segment(segment: Segment) -> Dict[str, str]:
        """Create a new segment"""
        logger.info(f"Creating segment: site={segment.site}, vlan_id={segment.vlan_id}, epg={segment.epg_name}")

        # Validate segment data
        await SegmentService._validate_segment_data(segment)

        # Check if VLAN ID already exists for this (network, site) combination
        if await DatabaseUtils.check_vlan_exists(segment.site, segment.vlan_id, segment.vrf):
            raise HTTPException(
                status_code=400,
                detail=f"VLAN {segment.vlan_id} already exists for network '{segment.vrf}' at site '{segment.site}'"
            )

        # Create the segment
        segment_data = SegmentService._segment_to_dict(segment)
        segment_id = await DatabaseUtils.create_segment(segment_data)

        logger.info(f"Created segment with ID: {segment_id}")
        return {"message": "Segment created", "id": segment_id}
    
    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("get_segment_by_id", threshold_ms=500)
    async def get_segment_by_id(segment_id: str) -> Dict[str, Any]:
        """Get a single segment by ID"""
        # Validate ObjectId format
        Validators.validate_object_id(segment_id)

        # Get the segment
        segment = await DatabaseUtils.get_segment_by_id(segment_id)
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        # Convert ObjectId to string (if not already a string)
        if not isinstance(segment["_id"], str):
            segment["_id"] = str(segment["_id"])

        logger.debug(f"Retrieved segment {segment_id}: site={segment.get('site')}, vlan_id={segment.get('vlan_id')}")
        return segment
    
    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("update_segment", threshold_ms=2000)
    async def update_segment(segment_id: str, updated_segment: Segment) -> Dict[str, str]:
        """Update a segment"""
        # Validate ObjectId format
        Validators.validate_object_id(segment_id)

        # Validate segment data (exclude self from overlap check)
        await SegmentService._validate_segment_data(updated_segment, exclude_id=segment_id)

        # Check if segment exists
        existing_segment = await DatabaseUtils.get_segment_by_id(segment_id)
        if not existing_segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        # VLAN ID is immutable - cannot be changed after creation
        if existing_segment["vlan_id"] != updated_segment.vlan_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "vlan_id_immutable",
                    "message": f"VLAN ID cannot be changed after creation",
                    "current_vlan_id": existing_segment["vlan_id"],
                    "attempted_vlan_id": updated_segment.vlan_id,
                    "suggestion": "Create a new segment with the desired VLAN ID and delete the old one if needed"
                }
            )

        # Check if site or VRF change would conflict (VLAN ID is already immutable)
        existing_vrf = existing_segment.get("vrf")
        if (existing_segment["site"] != updated_segment.site or
            existing_vrf != updated_segment.vrf):
            if await DatabaseUtils.check_vlan_exists_excluding_id(updated_segment.site, updated_segment.vlan_id, segment_id, updated_segment.vrf):
                raise HTTPException(
                    status_code=400,
                    detail=f"VLAN {updated_segment.vlan_id} already exists for network '{updated_segment.vrf}' at site '{updated_segment.site}'"
                )

        # Update the segment
        update_data = SegmentService._segment_to_dict(updated_segment)
        success = await DatabaseUtils.update_segment_by_id(segment_id, update_data)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update segment")

        logger.info(f"Updated segment {segment_id}")
        return {"message": "Segment updated successfully"}

    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("update_segment_clusters", threshold_ms=2000)
    async def update_segment_clusters(segment_id: str, cluster_names: str) -> Dict[str, str]:
        """Update cluster assignment for a segment (for shared segments)"""
        from datetime import datetime, timezone
        logger.info(f"Updating cluster assignment for segment: {segment_id}")

        # Validate ObjectId format
        Validators.validate_object_id(segment_id)

        # Check if segment exists
        existing_segment = await DatabaseUtils.get_segment_by_id(segment_id)
        if not existing_segment:
            logger.warning(f"Segment not found: {segment_id}")
            raise HTTPException(status_code=404, detail="Segment not found")

        # Clean up cluster names
        clean_cluster_names = cluster_names.strip() if cluster_names else None

        # Update the segment cluster assignment
        update_data = {}
        if clean_cluster_names:
            # Validate cluster names format (comma-separated, no special chars)
            cluster_list = [name.strip() for name in clean_cluster_names.split(",")]
            validated_clusters = []
            for cluster in cluster_list:
                if cluster and cluster.replace("-", "").replace("_", "").isalnum():
                    validated_clusters.append(cluster)

            if validated_clusters:
                update_data["cluster_name"] = ",".join(validated_clusters)
                update_data["allocated_at"] = datetime.now(timezone.utc)
                update_data["released"] = False
                update_data["released_at"] = None
            else:
                # No valid clusters, release the segment
                update_data["cluster_name"] = None
                update_data["released"] = True
                update_data["released_at"] = datetime.now(timezone.utc)
        else:
            # Empty cluster names, release the segment
            update_data["cluster_name"] = None
            update_data["released"] = True
            update_data["released_at"] = datetime.now(timezone.utc)

        success = await DatabaseUtils.update_segment_by_id(segment_id, update_data)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update segment clusters")

        logger.info(f"Updated cluster assignment for segment {segment_id}")
        return {"message": "Segment cluster assignment updated successfully"}

    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("delete_segment", threshold_ms=2000)
    async def delete_segment(segment_id: str) -> Dict[str, str]:
        """Delete a segment"""
        # Validate ObjectId format
        Validators.validate_object_id(segment_id)

        # Check if segment exists and is not allocated
        segment = await DatabaseUtils.get_segment_by_id(segment_id)
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        # Validate segment can be deleted
        Validators.validate_segment_not_allocated(segment)

        # Delete the segment
        success = await DatabaseUtils.delete_segment_by_id(segment_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete segment")

        logger.info(f"Deleted segment {segment_id}")
        return {"message": "Segment deleted"}
    
    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=2)  # Fewer retries for bulk operations
    @log_operation_timing("create_segments_bulk", threshold_ms=10000)  # Higher threshold for bulk
    async def create_segments_bulk(segments: List[Segment]) -> Dict[str, Any]:
        """Create multiple segments at once - OPTIMIZED: fetches existing segments once"""
        logger.info(f"Bulk creating {len(segments)} segments")

        if not segments or len(segments) == 0:
            logger.warning("Bulk create called with empty segments list")
            raise HTTPException(status_code=400, detail="No valid segments found in CSV data. Please check the format: site,vlan_id,epg_name,segment,vrf,dhcp,description")

        try:
            # OPTIMIZATION: Fetch existing segments ONCE for all validations
            existing_segments = await DatabaseUtils.get_segments_with_filters()

            created = 0
            errors = []
            # Track created segments within this bulk operation to detect duplicates in CSV
            created_in_bulk = set()

            for idx, segment in enumerate(segments, start=1):
                try:
                    logger.debug(f"Processing segment {idx}/{len(segments)}: site={segment.site}, vlan_id={segment.vlan_id}, segment={segment.segment}")

                    # Check for duplicates within this bulk request first (network+site+vlan scope)
                    segment_key = (segment.vrf, segment.site, segment.vlan_id)
                    if segment_key in created_in_bulk:
                        error_msg = f"Duplicate entry: VLAN {segment.vlan_id} for network '{segment.vrf}' at site '{segment.site}' appears multiple times in CSV"
                        logger.warning(f"Row {idx}: {error_msg}")
                        errors.append(error_msg)
                        continue

                    # Validate segment data (uses pre-fetched existing_segments, passed via closure)
                    await SegmentService._validate_segment_data(segment)

                    # Check if VLAN ID already exists - check in cached existing_segments
                    vlan_exists = any(
                        s.get("site") == segment.site and
                        s.get("vlan_id") == segment.vlan_id and
                        s.get("vrf") == segment.vrf
                        for s in existing_segments
                    )
                    if vlan_exists:
                        error_msg = f"VLAN {segment.vlan_id} already exists for network '{segment.vrf}' at site '{segment.site}'"
                        logger.warning(f"Row {idx}: {error_msg}")
                        errors.append(error_msg)
                        continue

                    # Create the segment
                    segment_data = SegmentService._segment_to_dict(segment)
                    new_segment = await DatabaseUtils.create_segment(segment_data)

                    # Add to tracking sets
                    created_in_bulk.add(segment_key)
                    # Update cached existing_segments for next iteration
                    existing_segments.append(new_segment if isinstance(new_segment, dict) else segment_data)
                    created += 1
                    logger.debug(f"Successfully created segment {idx}: site={segment.site}, vlan_id={segment.vlan_id}")

                except HTTPException as e:
                    error_msg = f"Row {idx} (Site {segment.site}, VLAN {segment.vlan_id}): {e.detail}"
                    logger.error(f"Validation error for segment {idx}: {error_msg}", exc_info=True)
                    errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Row {idx} (Site {segment.site}, VLAN {segment.vlan_id}): {str(e)}"
                    logger.error(f"Error creating segment {idx}: {error_msg}", exc_info=True)
                    errors.append(error_msg)

            logger.info(f"Bulk creation complete: {created} created, {len(errors)} errors")

            return {
                "message": f"Created {created} segments",
                "created": created,
                "errors": errors if errors else None
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in bulk creation: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("get_vrfs", threshold_ms=1000)
    async def get_vrfs() -> Dict[str, Any]:
        """Get list of available VRFs from NetBox"""
        vrfs = await DatabaseUtils.get_vrfs()
        logger.debug(f"Retrieved {len(vrfs)} VRFs")
        return {"vrfs": vrfs}