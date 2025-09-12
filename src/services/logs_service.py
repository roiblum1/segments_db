import logging
import os
from typing import Dict, Any
from fastapi import HTTPException
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

class LogsService:
    """Service class for log management operations"""
    
    @staticmethod
    async def get_logs(lines: int = 100) -> PlainTextResponse:
        """Get the contents of the vlan_manager.log file"""
        log_file_path = "vlan_manager.log"
        
        try:
            if not os.path.exists(log_file_path):
                return PlainTextResponse(
                    content="Log file not found. The application may not have started yet or logging is not configured properly.",
                    status_code=404
                )
            
            with open(log_file_path, 'r', encoding='utf-8') as f:
                log_lines = f.readlines()
            
            # Get the last N lines
            if lines > 0:
                log_lines = log_lines[-lines:]
            
            log_content = ''.join(log_lines)
            
            return PlainTextResponse(
                content=log_content,
                media_type="text/plain"
            )
            
        except PermissionError:
            logger.error(f"Permission denied accessing log file: {log_file_path}")
            raise HTTPException(
                status_code=403, 
                detail="Permission denied accessing log file"
            )
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error reading log file: {str(e)}"
            )
    
    @staticmethod
    async def get_log_info() -> Dict[str, Any]:
        """Get information about the log file"""
        log_file_path = "vlan_manager.log"
        
        try:
            if not os.path.exists(log_file_path):
                return {
                    "exists": False,
                    "message": "Log file not found"
                }
            
            stat = os.stat(log_file_path)
            
            return {
                "exists": True,
                "file_path": os.path.abspath(log_file_path),
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "last_modified": stat.st_mtime,
                "lines_available": "Use /api/logs?lines=N to view last N lines"
            }
            
        except Exception as e:
            logger.error(f"Error getting log info: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error getting log information: {str(e)}"
            )