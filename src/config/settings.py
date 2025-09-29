import os
import logging
import sys

# Database Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb+srv://roiblum05:0548818978@test.ymcnygm.mongodb.net/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "vlan_manager")

# SSL Configuration for MongoDB (disable certificate verification)
MONGODB_SSL_SETTINGS = {
    "tls": True,
    "tlsAllowInvalidCertificates": True,
    "tlsAllowInvalidHostnames": True
}

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
    """Configure logging for the application"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('vlan_manager.log')
        ]
    )
    return logging.getLogger(__name__)

# Server Configuration
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000