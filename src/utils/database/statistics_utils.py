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
        """Get statistics for a specific site"""
        storage = get_storage()

        total_segments = await storage.count_documents({"site": site})
        allocated = await storage.count_documents({
            "site": site,
            "cluster_name": {"$ne": None},
            "released": False
        })

        return {
            "site": site,
            "total_segments": total_segments,
            "allocated": allocated,
            "available": total_segments - allocated,
            "utilization": round((allocated / total_segments * 100) if total_segments > 0 else 0, 1)
        }
