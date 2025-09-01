"""
Main FastAPI application for Network Segment Manager.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import init_db, get_db
from app.core.logging import setup_logging, get_logger
from app.models.segment import Segment
from app.api.segments import router as segments_router


# Setup logging
setup_logging()
logger = get_logger("main")


async def load_sample_data():
    """Load sample data if enabled and database is empty."""
    if not settings.load_sample_data:
        logger.info("Sample data loading disabled")
        return
    
    try:
        with get_db() as db:
            count = db.query(Segment).count()
            
            if count == 0:
                logger.info("Database empty, initializing with sample data")
                
                sample_segments = [
                    # Office1 segments
                    Segment(
                        zone="Office1",
                        vlan_id=100, 
                        epg_name="Production-EPG", 
                        segment="10.100.0.0/24", 
                        cluster_using=None, 
                        in_use=False
                    ),
                    Segment(
                        zone="Office1",
                        vlan_id=101, 
                        epg_name="Production-EPG", 
                        segment="10.100.1.0/24", 
                        cluster_using="office1-prod-cluster", 
                        in_use=True
                    ),
                    Segment(
                        zone="Office1",
                        vlan_id=102, 
                        epg_name="Development-EPG", 
                        segment="10.101.0.0/24", 
                        cluster_using="office1-dev-cluster", 
                        in_use=True
                    ),
                    Segment(
                        zone="Office1",
                        vlan_id=103, 
                        epg_name="Testing-EPG", 
                        segment="10.102.0.0/24", 
                        cluster_using=None, 
                        in_use=False
                    ),
                    
                    # Office2 segments
                    Segment(
                        zone="Office2",
                        vlan_id=100, 
                        epg_name="Production-EPG", 
                        segment="10.200.0.0/24", 
                        cluster_using="office2-prod-cluster", 
                        in_use=True
                    ),
                    Segment(
                        zone="Office2",
                        vlan_id=101, 
                        epg_name="Production-EPG", 
                        segment="10.200.1.0/24", 
                        cluster_using=None, 
                        in_use=False
                    ),
                    Segment(
                        zone="Office2",
                        vlan_id=102, 
                        epg_name="Development-EPG", 
                        segment="10.201.0.0/24", 
                        cluster_using=None, 
                        in_use=False
                    ),
                    Segment(
                        zone="Office2",
                        vlan_id=103, 
                        epg_name="Testing-EPG", 
                        segment="10.202.0.0/24", 
                        cluster_using="office2-test-cluster", 
                        in_use=True
                    ),
                    
                    # Office3 segments
                    Segment(
                        zone="Office3",
                        vlan_id=100, 
                        epg_name="Production-EPG", 
                        segment="10.50.0.0/24", 
                        cluster_using=None, 
                        in_use=False
                    ),
                    Segment(
                        zone="Office3",
                        vlan_id=101, 
                        epg_name="Production-EPG", 
                        segment="10.50.1.0/24", 
                        cluster_using=None, 
                        in_use=False
                    ),
                    Segment(
                        zone="Office3",
                        vlan_id=102, 
                        epg_name="Development-EPG", 
                        segment="10.51.0.0/24", 
                        cluster_using="office3-dev-cluster", 
                        in_use=True
                    ),
                    Segment(
                        zone="Office3",
                        vlan_id=103, 
                        epg_name="Testing-EPG", 
                        segment="10.52.0.0/24", 
                        cluster_using=None, 
                        in_use=False
                    ),
                ]
                
                for segment in sample_segments:
                    db.add(segment)
                
                db.commit()
                logger.info(f"Initialized database with {len(sample_segments)} sample segments")
            else:
                logger.info(f"Database already contains {count} segments, skipping sample data")
                
    except SQLAlchemyError as e:
        logger.error(f"Database error loading sample data: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading sample data: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    
    try:
        # Initialize database
        init_db()
        logger.info("Database initialized successfully")
        
        # Load sample data if needed
        await load_sample_data()
        
        logger.info("Application startup completed")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="API for managing network segments for OpenShift/Hypershift clusters",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=settings.allowed_methods,
    allow_headers=settings.allowed_headers,
)

# Include API routers
app.include_router(segments_router)

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    logger.info(f"Static files mounted from {static_path}")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main UI."""
    try:
        index_path = Path(__file__).parent / "static" / "index.html"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.debug("Served main UI from index.html")
            return content
        else:
            logger.warning("index.html not found in static directory")
            raise HTTPException(status_code=404, detail="UI not found")
    except Exception as e:
        logger.error(f"Error serving main UI: {e}")
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Network Segment Manager</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .error { color: #d32f2f; background: #ffebee; padding: 20px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <h1>Network Segment Manager</h1>
            <div class="error">
                <p>UI is temporarily unavailable. Please use the API documentation at <a href="/docs">/docs</a></p>
            </div>
        </body>
        </html>
        """


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        from sqlalchemy import text
        with get_db() as db:
            db.execute(text("SELECT 1"))
        
        return {
            "status": "healthy",
            "app_name": settings.app_name,
            "version": settings.app_version,
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting application with uvicorn")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower()
    )