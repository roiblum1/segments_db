import logging
import io
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from ..utils.database_utils import DatabaseUtils

logger = logging.getLogger(__name__)

class ExportService:
    """Service class for data export operations"""
    
    @staticmethod
    async def export_segments_csv(site: Optional[str] = None, allocated: Optional[bool] = None) -> StreamingResponse:
        """Export segments data as CSV"""
        try:
            segments = await DatabaseUtils.get_segments_with_filters(site=site, allocated=allocated)
            
            # Prepare data for export
            export_data = []
            for segment in segments:
                export_data.append({
                    'Site': segment.get('site', ''),
                    'VLAN ID': segment.get('vlan_id', ''),
                    'EPG Name': segment.get('epg_name', ''),
                    'Segment': segment.get('segment', ''),
                    'Description': segment.get('description', ''),
                    'Cluster Name': segment.get('cluster_name', '') if segment.get('cluster_name') else 'Available',
                    'Allocated At': segment.get('allocated_at', ''),
                    'Released': 'Yes' if segment.get('released', False) else 'No',
                    'Released At': segment.get('released_at', ''),
                    'Status': 'Allocated' if segment.get('cluster_name') and not segment.get('released', False) else 'Available'
                })
            
            # Create DataFrame
            df = pd.DataFrame(export_data)
            
            # Convert to CSV
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_content = csv_buffer.getvalue()
            csv_buffer.close()
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            site_suffix = f"_{site}" if site else ""
            allocated_suffix = "_allocated" if allocated is True else "_available" if allocated is False else ""
            filename = f"segments{site_suffix}{allocated_suffix}_{timestamp}.csv"
            
            # Return streaming response
            return StreamingResponse(
                io.BytesIO(csv_content.encode('utf-8')),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
        except Exception as e:
            logger.error(f"Error exporting segments to CSV: {e}")
            raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    
    @staticmethod
    async def export_segments_excel(site: Optional[str] = None, allocated: Optional[bool] = None) -> StreamingResponse:
        """Export segments data as Excel"""
        try:
            segments = await DatabaseUtils.get_segments_with_filters(site=site, allocated=allocated)
            
            # Prepare data for export
            export_data = []
            for segment in segments:
                export_data.append({
                    'Site': segment.get('site', ''),
                    'VLAN ID': segment.get('vlan_id', ''),
                    'EPG Name': segment.get('epg_name', ''),
                    'Segment': segment.get('segment', ''),
                    'Description': segment.get('description', ''),
                    'Cluster Name': segment.get('cluster_name', '') if segment.get('cluster_name') else 'Available',
                    'Allocated At': segment.get('allocated_at', ''),
                    'Released': 'Yes' if segment.get('released', False) else 'No',
                    'Released At': segment.get('released_at', ''),
                    'Status': 'Allocated' if segment.get('cluster_name') and not segment.get('released', False) else 'Available'
                })
            
            # Create DataFrame
            df = pd.DataFrame(export_data)
            
            # Convert to Excel
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Segments', index=False)
                
                # Auto-adjust column widths
                worksheet = writer.sheets['Segments']
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
            
            excel_buffer.seek(0)
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            site_suffix = f"_{site}" if site else ""
            allocated_suffix = "_allocated" if allocated is True else "_available" if allocated is False else ""
            filename = f"segments{site_suffix}{allocated_suffix}_{timestamp}.xlsx"
            
            # Return streaming response
            return StreamingResponse(
                excel_buffer,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
        except Exception as e:
            logger.error(f"Error exporting segments to Excel: {e}")
            raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    
    @staticmethod
    async def export_stats_csv() -> StreamingResponse:
        """Export site statistics as CSV"""
        try:
            from ..config.settings import SITES
            
            # Get stats for all sites
            stats_data = []
            for site in SITES:
                stats = await DatabaseUtils.get_site_statistics(site)
                stats_data.append(stats)
            
            # Create DataFrame
            df = pd.DataFrame(stats_data)
            
            # Convert to CSV
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_content = csv_buffer.getvalue()
            csv_buffer.close()
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"site_statistics_{timestamp}.csv"
            
            # Return streaming response
            return StreamingResponse(
                io.BytesIO(csv_content.encode('utf-8')),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
        except Exception as e:
            logger.error(f"Error exporting stats to CSV: {e}")
            raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")