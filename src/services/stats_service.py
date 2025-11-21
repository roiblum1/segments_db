import logging
from typing import List, Dict, Any
from datetime import datetime
from fastapi import HTTPException

from ..utils.database_utils import DatabaseUtils
from ..config.settings import SITES
from ..utils.error_handlers import handle_netbox_errors, retry_on_network_error
from ..utils.logging_decorators import log_operation_timing

logger = logging.getLogger(__name__)

class StatsService:
    """Service class for statistics operations"""
    
    @staticmethod
    async def get_sites() -> Dict[str, List[str]]:
        """Get configured sites"""
        return {"sites": SITES}
    
    @staticmethod
    @handle_netbox_errors
    @retry_on_network_error(max_retries=3)
    @log_operation_timing("get_stats", threshold_ms=1000)
    async def get_stats() -> List[Dict[str, Any]]:
        """Get statistics per site"""
        stats = []

        for site in SITES:
            site_stats = await DatabaseUtils.get_site_statistics(site)
            stats.append(site_stats)

        return stats
    
    @staticmethod
    @handle_netbox_errors
    @log_operation_timing("health_check", threshold_ms=2000)
    async def health_check() -> Dict[str, Any]:
        """Enhanced health check endpoint with comprehensive system validation"""
        from ..database.netbox_client import get_netbox_client
        from ..config.settings import NETBOX_URL

        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "sites": SITES,
            "storage_type": "netbox",
            "netbox_url": NETBOX_URL
        }

        # Check NetBox connectivity
        nb = get_netbox_client()
        status = nb.status()

        health_data["storage"] = "accessible"
        health_data["netbox_version"] = status.get("netbox-version")
        health_data["netbox_status"] = "connected"

        # Test database operations - Get total segments count
        total_segments = 0
        site_counts = {}

        for site in SITES:
            try:
                site_stats = await DatabaseUtils.get_site_statistics(site)
                site_total = site_stats.get("total_segments", 0)
                total_segments += site_total

                site_counts[site] = {
                    "total": site_total,
                    "allocated": site_stats.get("allocated", 0),
                    "available": site_stats.get("available", 0),
                    "utilization": site_stats.get("utilization", 0)
                }
            except Exception as site_error:
                logger.warning(f"Error getting stats for site {site}: {site_error}")
                site_counts[site] = {"error": str(site_error)}

        health_data["total_segments"] = total_segments
        health_data["sites_summary"] = site_counts

        # Test basic query operations
        try:
            recent_segments = await DatabaseUtils.get_segments_with_filters()
            health_data["storage_operations"] = "working"
            health_data["sample_query_success"] = True
            health_data["sample_segments_found"] = len(recent_segments)
        except Exception as query_error:
            health_data["storage_operations"] = "limited"
            health_data["sample_query_success"] = False
            health_data["query_error"] = str(query_error)

        # Overall system health summary
        total_sites = len(SITES)
        health_data["system_summary"] = {
            "configured_sites": total_sites,
            "total_segments": total_segments,
            "average_segments_per_site": round(total_segments / total_sites, 2) if total_sites > 0 else 0
        }

        return health_data