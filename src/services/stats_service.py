import logging
from typing import List, Dict, Any
from datetime import datetime
from fastapi import HTTPException

from ..utils.database_utils import DatabaseUtils
from ..config.settings import SITES

logger = logging.getLogger(__name__)

class StatsService:
    """Service class for statistics operations"""
    
    @staticmethod
    async def get_sites() -> Dict[str, List[str]]:
        """Get configured sites"""
        return {"sites": SITES}
    
    @staticmethod
    async def get_stats() -> List[Dict[str, Any]]:
        """Get statistics per site"""
        try:
            stats = []
            
            for site in SITES:
                site_stats = await DatabaseUtils.get_site_statistics(site)
                stats.append(site_stats)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @staticmethod
    async def health_check() -> Dict[str, Any]:
        """Enhanced health check endpoint with comprehensive system validation"""
        from ..config.settings import STORAGE_BACKEND, MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE

        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "sites": SITES,
            "storage_type": STORAGE_BACKEND
        }

        # Add storage-specific information
        if STORAGE_BACKEND == "mysql":
            health_data["mysql_host"] = MYSQL_HOST
            health_data["mysql_port"] = MYSQL_PORT
            health_data["mysql_database"] = MYSQL_DATABASE
        else:
            from ..config.settings import NETBOX_URL
            health_data["netbox_url"] = NETBOX_URL

        try:
            # Check storage connectivity
            if STORAGE_BACKEND == "mysql":
                # Test MySQL connectivity
                from ..database.mysql_storage import get_mysql_pool
                pool = await get_mysql_pool()
                health_data["storage"] = "accessible"
                health_data["mysql_status"] = "connected"
            else:
                # Check NetBox connectivity
                from ..database.netbox_storage import get_netbox_client
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

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_data.update({
                "status": "unhealthy",
                "storage": "error",
                "error": str(e)
            })

        return health_data