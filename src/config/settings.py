import os
import logging
import sys

# Storage Backend Selection
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "mysql").lower()  # "mysql" or "netbox"

# MySQL Configuration (Primary Storage)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "vlan_manager")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "vlan_manager_password")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "vlan_manager")
MYSQL_POOL_SIZE = int(os.getenv("MYSQL_POOL_SIZE", "20"))

# NetBox Configuration (Legacy - kept for reference)
NETBOX_URL = os.getenv("NETBOX_URL", "https://srcc3192.cloud.netboxapp.com")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN", "892ee583fa47f1682ef258f8df00fbeea11f6ebc")
NETBOX_SSL_VERIFY = os.getenv("NETBOX_SSL_VERIFY", "true").lower() in ("true", "1", "yes")

# Sites Configuration
SITES = os.getenv("SITES", "site1,site2,site3").split(",")
SITES = [s.strip() for s in SITES if s.strip()]

# Site IP Prefix Configuration
# Format: "site1:192,site2:193,site3:194"
SITE_PREFIXES_ENV = os.getenv("SITE_PREFIXES", "site1:192,site2:193,site3:194")

def parse_site_prefixes(site_prefixes_str: str) -> dict:
    """Parse site prefixes from environment variable"""
    prefixes = {}
    for pair in site_prefixes_str.split(","):
        if ":" in pair:
            site, prefix = pair.strip().split(":", 1)
            prefixes[site.strip()] = prefix.strip()
    return prefixes

SITE_IP_PREFIXES = parse_site_prefixes(SITE_PREFIXES_ENV)

def validate_site_prefixes():
    """Validate that all configured sites have IP prefixes defined"""
    missing_prefixes = []
    
    for site in SITES:
        if site not in SITE_IP_PREFIXES:
            missing_prefixes.append(site)
    
    if missing_prefixes:
        error_msg = (
            f"CRITICAL CONFIGURATION ERROR: Sites {missing_prefixes} are missing IP prefixes!\n"
            f"Configured sites: {SITES}\n"
            f"Available prefixes: {list(SITE_IP_PREFIXES.keys())}\n"
            f"Please add missing prefixes to SITE_PREFIXES environment variable.\n"
            f"Example: SITE_PREFIXES=\"site1:192,site2:193,site3:194\""
        )
        
        # Log error and crash the application
        print(f"ERROR: {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)

def get_site_prefix(site: str) -> str:
    """Get the IP prefix for a given site"""
    return SITE_IP_PREFIXES.get(site, "192")

# Logging Configuration
def setup_logging():
    """Configure logging for the application with rotation"""
    from logging.handlers import RotatingFileHandler

    # Get log level from environment variable, default to INFO
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Create rotating file handler: 50MB per file, keep 5 backup files
    rotating_handler = RotatingFileHandler(
        'vlan_manager.log',
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,  # Keep 5 backup files (total ~250MB)
        encoding='utf-8'
    )

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] %(funcName)s() - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            rotating_handler
        ]
    )
    return logging.getLogger(__name__)

# Server Configuration
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))