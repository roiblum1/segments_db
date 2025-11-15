#!/usr/bin/env python3
"""
Database Initialization Script
Initializes MySQL database with schema and default data
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.config.settings import (
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
)
import aiomysql


async def init_database():
    """Initialize database with schema"""
    print(f"Initializing database: {MYSQL_DATABASE} on {MYSQL_HOST}:{MYSQL_PORT}")

    try:
        # Connect to MySQL server (not specific database)
        conn = await aiomysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            charset='utf8mb4'
        )

        cursor = await conn.cursor()

        # Create database if not exists
        await cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"✓ Database '{MYSQL_DATABASE}' created/verified")

        # Use the database
        await cursor.execute(f"USE {MYSQL_DATABASE}")

        # Read and execute schema
        schema_path = os.path.join(os.path.dirname(__file__), 'src', 'database', 'mysql_schema.sql')

        if not os.path.exists(schema_path):
            print(f"✗ Schema file not found: {schema_path}")
            return False

        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        # Split by semicolons and execute each statement
        statements = [s.strip() for s in schema_sql.split(';') if s.strip() and not s.strip().startswith('--')]

        for statement in statements:
            # Skip USE database and CREATE DATABASE statements
            if statement.upper().startswith('USE ') or statement.upper().startswith('CREATE DATABASE'):
                continue

            try:
                await cursor.execute(statement)
                await conn.commit()
            except Exception as e:
                print(f"Warning executing statement: {e}")
                # Continue anyway, table might already exist

        print("✓ Database schema initialized")

        await cursor.close()
        conn.close()

        print("\n✅ Database initialization complete!")
        print(f"\nConnection details:")
        print(f"  Host: {MYSQL_HOST}")
        print(f"  Port: {MYSQL_PORT}")
        print(f"  Database: {MYSQL_DATABASE}")
        print(f"  User: {MYSQL_USER}")

        return True

    except Exception as e:
        print(f"\n✗ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(init_database())
    sys.exit(0 if success else 1)
