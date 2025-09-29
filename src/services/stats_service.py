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
        from ..database.mongodb import motor_client
        
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "sites": SITES
        }
        
        try:
            # Check MongoDB connection
            await motor_client.server_info()
            health_data["database"] = "connected"
            
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
                recent_segments = await DatabaseUtils.get_segments_with_filters(limit=1)
                health_data["database_operations"] = "working"
                health_data["sample_query_success"] = True
            except Exception as query_error:
                health_data["database_operations"] = "limited"
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
                "database": "disconnected",
                "error": str(e)
            })
            
        return health_data