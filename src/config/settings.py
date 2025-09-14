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