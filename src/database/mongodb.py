import logging
from motor.motor_asyncio import AsyncIOMotorClient
from ..config.settings import MONGODB_URL, DATABASE_NAME, MONGODB_SSL_SETTINGS

logger = logging.getLogger(__name__)

# Global database variables
motor_client = None
db = None
segments_collection = None

async def connect_to_mongo():
    """Connect to MongoDB and initialize collections"""
    global motor_client, db, segments_collection
    
    try:
        motor_client = AsyncIOMotorClient(
            MONGODB_URL, 
            serverSelectionTimeoutMS=5000,
            **MONGODB_SSL_SETTINGS
        )
        # Test connection
        await motor_client.server_info()
        logger.info("Successfully connected to MongoDB with insecure SSL")
        
        db = motor_client[DATABASE_NAME]
        segments_collection = db["segments"]
        
        # Initialize database with indexes
        await init_db()
        logger.info(f"Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def close_mongo_connection():
    """Close MongoDB connection"""
    global motor_client
    if motor_client:
        motor_client.close()
        logger.info("MongoDB connection closed")

async def init_db():
    """Initialize database with indexes"""
    global segments_collection
    try:
        # Create indexes
        await segments_collection.create_index([("site", 1), ("vlan_id", 1)], unique=True)
        await segments_collection.create_index([("cluster_name", 1)])
        await segments_collection.create_index([("site", 1), ("released", 1)])
        await segments_collection.create_index([("epg_name", 1)])
        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")

def get_segments_collection():
    """Get the segments collection"""
    return segments_collection