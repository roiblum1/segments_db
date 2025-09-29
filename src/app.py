from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config.settings import setup_logging, SITES, validate_site_prefixes
from .database.mongodb import connect_to_mongo, close_mongo_connection
from .api.routes import router

# Setup logging
logger = setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        # Validate site prefixes configuration before anything else
        logger.info("Validating site prefixes configuration...")
        validate_site_prefixes()
        logger.info("Site prefixes validation passed")
        
        await connect_to_mongo()
        logger.info(f"Database initialized. Managing sites: {SITES}")
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    
    yield
    
    # Shutdown
    await close_mongo_connection()

# FastAPI app - used by uvicorn server
app = FastAPI(title="VLAN Manager API", lifespan=lifespan)

# Custom StaticFiles class with caching headers
class CachedStaticFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        
        # Convert to Path object and get file extension
        path = Path(full_path)
        file_extension = path.suffix.lower()
        
        # Add cache headers for static assets
        if file_extension in ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg']:
            # Cache for 1 year (static assets with versioning)
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif file_extension in ['.html']:
            # Cache HTML for 1 hour but allow revalidation
            response.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
        else:
            # Default cache for other files
            response.headers["Cache-Control"] = "public, max-age=86400"  # 1 day
            
        return response

# Mount static files with caching
app.mount("/static", CachedStaticFiles(directory="static"), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# HTML UI - Serve static HTML file
@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("static/html/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: index.html not found</h1>", status_code=500)