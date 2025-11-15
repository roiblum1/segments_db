"""
MySQL Connection Manager
Handles connection pooling and pool lifecycle
"""
import logging
from typing import Optional
import aiomysql

from ..config.settings import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_DATABASE,
    MYSQL_USER,
    MYSQL_PASSWORD
)

logger = logging.getLogger(__name__)

# Global connection pool
_mysql_pool: Optional[aiomysql.Pool] = None


async def get_mysql_pool() -> aiomysql.Pool:
    """
    Get or create the MySQL connection pool

    Returns:
        aiomysql.Pool instance

    Raises:
        Exception: If pool creation fails
    """
    global _mysql_pool

    if _mysql_pool is None:
        logger.info(
            f"Creating MySQL connection pool: "
            f"{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
        )

        _mysql_pool = await aiomysql.create_pool(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DATABASE,
            autocommit=True,  # Immediate transaction commits
            minsize=5,
            maxsize=20,
            echo=False
        )

        logger.info(
            f"MySQL connection pool created successfully "
            f"(min=5, max=20, autocommit=True)"
        )

    return _mysql_pool


async def close_mysql_pool():
    """
    Close the MySQL connection pool

    Closes all connections and releases resources
    """
    global _mysql_pool

    if _mysql_pool is not None:
        logger.info("Closing MySQL connection pool")
        _mysql_pool.close()
        await _mysql_pool.wait_closed()
        _mysql_pool = None
        logger.info("MySQL connection pool closed")


async def init_connection():
    """Initialize MySQL connection pool"""
    await get_mysql_pool()
    logger.info("MySQL connection initialized")


async def close_connection():
    """Close MySQL connection pool"""
    await close_mysql_pool()
    logger.info("MySQL connection closed")
