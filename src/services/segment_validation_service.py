"""
Segment Validation Service
Handles all validation logic for segment operations
"""
import logging
from typing import Optional, List, Dict, Any

from ..models.schemas import Segment
from ..utils.validators import Validators

logger = logging.getLogger(__name__)


class SegmentValidationService:
    """Service for segment validation operations"""

    @staticmethod
    async def validate_segment_data(
        segment: Segment,
        existing_segments: List[Dict[str, Any]],
        exclude_id: Optional[str] = None
    ) -> None:
        """
        Validate all segment data before create/update operations

        Args:
            segment: Segment data to validate
            existing_segments: All existing segments for overlap/uniqueness checks
            exclude_id: ID to exclude from validation (for updates)

        Raises:
            HTTPException: If validation fails
        """
        # Basic field validation
        SegmentValidationService._validate_basic_fields(segment)

        # Network validation
        SegmentValidationService._validate_network_fields(segment)

        # Security validation
        SegmentValidationService._validate_security(segment)

        # Filter out the segment being updated from validation checks
        filtered_segments = existing_segments
        if exclude_id:
            filtered_segments = [
                s for s in existing_segments
                if str(s.get("_id")) != str(exclude_id)
            ]

        # Cross-segment validation
        SegmentValidationService._validate_uniqueness(segment, filtered_segments)

    @staticmethod
    def _validate_basic_fields(segment: Segment) -> None:
        """Validate basic segment fields"""
        Validators.validate_site(segment.site)
        Validators.validate_epg_name(segment.epg_name)
        Validators.validate_vlan_id(segment.vlan_id)

    @staticmethod
    def _validate_network_fields(segment: Segment) -> None:
        """Validate network-related fields"""
        Validators.validate_segment_format(segment.segment, segment.site)
        Validators.validate_subnet_mask(segment.segment)
        Validators.validate_no_reserved_ips(segment.segment)
        Validators.validate_network_broadcast_gateway(segment.segment)

    @staticmethod
    def _validate_security(segment: Segment) -> None:
        """Validate security (XSS protection)"""
        # Description XSS protection
        if segment.description:
            Validators.validate_description(segment.description)
            Validators.validate_no_script_injection(segment.description, "description")

        # EPG name XSS protection
        Validators.validate_no_script_injection(segment.epg_name, "epg_name")

    @staticmethod
    def _validate_uniqueness(segment: Segment, existing_segments: List[Dict[str, Any]]) -> None:
        """Validate uniqueness constraints"""
        # IP overlap validation
        Validators.validate_ip_overlap(segment.segment, existing_segments)

        # EPG name uniqueness validation
        Validators.validate_vlan_name_uniqueness(
            site=segment.site,
            epg_name=segment.epg_name,
            vlan_id=segment.vlan_id,
            existing_segments=existing_segments,
            exclude_id=None  # Already filtered above
        )

    @staticmethod
    def validate_object_id(segment_id: str) -> None:
        """Validate segment ID format"""
        Validators.validate_object_id(segment_id)

    @staticmethod
    def validate_segment_not_allocated(segment: Dict[str, Any]) -> None:
        """Validate segment is not allocated before deletion"""
        Validators.validate_segment_not_allocated(segment)

    @staticmethod
    def validate_cluster_names(cluster_names: str) -> Optional[str]:
        """
        Validate and clean cluster names format

        Args:
            cluster_names: Comma-separated cluster names

        Returns:
            Cleaned cluster names string or None if invalid
        """
        if not cluster_names or not cluster_names.strip():
            return None

        # Parse comma-separated cluster names
        cluster_list = [name.strip() for name in cluster_names.split(",")]
        validated_clusters = []

        for cluster in cluster_list:
            # Allow alphanumeric, hyphens, and underscores
            if cluster and cluster.replace("-", "").replace("_", "").isalnum():
                validated_clusters.append(cluster)
            else:
                logger.warning(f"Invalid cluster name format: {cluster}")

        return ",".join(validated_clusters) if validated_clusters else None
