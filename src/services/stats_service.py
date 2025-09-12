import logging
from typing import List, Dict, Any
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
        """Health check endpoint"""
        from ..database.mongodb import motor_client
        
        try:
            # Check MongoDB connection
            await motor_client.server_info()
            return {
                "status": "healthy",
                "database": "connected",
                "sites": SITES
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e)
            }