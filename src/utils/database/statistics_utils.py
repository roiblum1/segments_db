"""Statistics and aggregation utilities for VLAN segments.

Handles calculation of site statistics and utilization metrics.
"""

import logging
from typing import Dict, Any

from ...database.netbox_storage import get_storage

logger = logging.getLogger(__name__)


class StatisticsUtils:
    """Statistics and aggregation for segments"""

    @staticmethod
    async def get_site_statistics(site: str) -> Dict[str, Any]:
        """Get statistics for a specific site

        Optimized to use single query instead of multiple count_documents calls.
        This is more efficient because:
        1. Fetches data from cache (prefixes cached for 10 minutes)
        2. Calculates counts in Python instead of additional API calls
        3. Reduces load on NetBox
        """
        storage = get_storage()

        # Single query instead of two count_documents calls
        segments = await storage.find({"site": site})

        total_segments = len(segments)
        allocated = sum(1 for s in segments
                       if s.get("cluster_name") and not s.get("released", False))

        return {
            "site": site,
            "total_segments": total_segments,
            "allocated": allocated,
            "available": total_segments - allocated,
            "utilization": round((allocated / total_segments * 100) if total_segments > 0 else 0, 1)
        }
