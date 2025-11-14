"""
MySQL Storage Implementation

This module provides a storage interface that uses MySQL database
for managing VLANs and IP prefixes (segments). It replaces NetBox
with a direct MySQL backend.

Tables Used:
- segments: IP address segments/subnets (main table)
- vlans: VLAN definitions
- vrfs: Virtual Routing and Forwarding (networks)
- site_groups: Site organizational grouping
- tenants: Tenant (fixed to "Redbull")
- roles: Prefix roles (fixed to "Data")
- vlan_groups: VLAN grouping by VRF and site

"""

import logging
import aiomysql
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import asyncio
import time
import re
from functools import lru_cache, wraps

from ..config.settings import (
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD,
    MYSQL_DATABASE, MYSQL_POOL_SIZE
)

logger = logging.getLogger(__name__)

# Global MySQL connection pool
_mysql_pool: Optional[aiomysql.Pool] = None

# Cache for frequently accessed data
_cache = {
    "segments": {"data": None, "timestamp": 0, "ttl": 600},  # 10 minutes
    "vrfs": {"data": None, "timestamp": 0, "ttl": 3600},  # 1 hour
    "redbull_tenant_id": {"data": None, "timestamp": 0, "ttl": 3600},
}

# Request coalescing (prevent duplicate concurrent fetches)
_inflight_requests = {}


def _get_cached(key: str) -> Optional[Any]:
    """Get cached data if still valid"""
    cache_entry = _cache.get(key)
    if cache_entry and cache_entry["data"] is not None:
        age = time.time() - cache_entry["timestamp"]
        if age < cache_entry["ttl"]:
            logger.debug(f"Cache HIT for {key} (age: {age:.1f}s)")
            return cache_entry["data"]
        else:
            logger.debug(f"Cache EXPIRED for {key} (age: {age:.1f}s, TTL: {cache_entry['ttl']}s)")
    return None


def _set_cache(key: str, data: Any) -> None:
    """Store data in cache with timestamp"""
    if key in _cache:
        _cache[key]["data"] = data
        _cache[key]["timestamp"] = time.time()
        logger.debug(f"Cache SET for {key} ({len(data) if isinstance(data, list) else 'N/A'} items)")


def invalidate_cache(key: Optional[str] = None) -> None:
    """Invalidate cache entries"""
    if key:
        if key in _cache:
            _cache[key]["data"] = None
            _cache[key]["timestamp"] = 0
            logger.info(f"Cache invalidated for {key}")
    else:
        for k in _cache:
            _cache[k]["data"] = None
            _cache[k]["timestamp"] = 0
        logger.info("All cache invalidated")


@lru_cache(maxsize=1)
async def get_mysql_pool() -> aiomysql.Pool:
    """Get or create MySQL connection pool (singleton)"""
    global _mysql_pool

    if _mysql_pool is None:
        logger.info(f"Creating MySQL pool: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}")
        _mysql_pool = await aiomysql.create_pool(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DATABASE,
            minsize=5,
            maxsize=MYSQL_POOL_SIZE,
            autocommit=False,
            charset='utf8mb4',
            connect_timeout=10
        )
        logger.info(f"MySQL pool created successfully (size: {MYSQL_POOL_SIZE})")

    return _mysql_pool


async def close_mysql_pool():
    """Close MySQL connection pool"""
    global _mysql_pool
    if _mysql_pool:
        _mysql_pool.close()
        await _mysql_pool.wait_closed()
        _mysql_pool = None
        logger.info("MySQL pool closed")


class MySQLStorage:
    """
    MySQL Storage implementation
    Provides the same interface as NetBoxStorage but uses MySQL backend
    """

    def __init__(self):
        self.pool = None

    async def _ensure_pool(self):
        """Ensure connection pool is initialized"""
        if self.pool is None:
            self.pool = await get_mysql_pool()

    async def _execute_query(self, query: str, params: tuple = None, fetch_one=False, fetch_all=False):
        """Execute a query with timing and error handling"""
        await self._ensure_pool()

        t_start = time.time()
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                try:
                    await cursor.execute(query, params or ())

                    if fetch_one:
                        result = await cursor.fetchone()
                    elif fetch_all:
                        result = await cursor.fetchall()
                    else:
                        await conn.commit()
                        result = cursor.lastrowid

                    elapsed = (time.time() - t_start) * 1000

                    if elapsed > 2000:
                        logger.warning(f"⚠️  MYSQL SLOW: query took {elapsed:.0f}ms")
                    else:
                        logger.debug(f"⏱️  MYSQL OK: query took {elapsed:.0f}ms")

                    return result

                except Exception as e:
                    await conn.rollback()
                    elapsed = (time.time() - t_start) * 1000
                    logger.error(f"MYSQL FAILED: query failed after {elapsed:.0f}ms - {e}")
                    raise

    # ==================== Helper Methods ====================

    async def _get_redbull_tenant_id(self) -> int:
        """Get Redbull tenant ID (cached)"""
        cached_id = _get_cached("redbull_tenant_id")
        if cached_id:
            return cached_id

        result = await self._execute_query(
            "SELECT id FROM tenants WHERE slug = %s",
            ('redbull',),
            fetch_one=True
        )

        if result:
            tenant_id = result['id']
            _set_cache("redbull_tenant_id", tenant_id)
            return tenant_id

        raise ValueError("Redbull tenant not found in database")

    async def _get_vrf_id(self, vrf_name: str) -> Optional[int]:
        """Get VRF ID by name"""
        result = await self._execute_query(
            "SELECT id FROM vrfs WHERE name = %s",
            (vrf_name,),
            fetch_one=True
        )
        return result['id'] if result else None

    async def _get_or_create_site_group(self, site: str) -> int:
        """Get or create site group"""
        slug = site.lower().replace('_', '-')

        # Try to get existing
        result = await self._execute_query(
            "SELECT id FROM site_groups WHERE slug = %s",
            (slug,),
            fetch_one=True
        )

        if result:
            return result['id']

        # Create new
        site_group_id = await self._execute_query(
            "INSERT INTO site_groups (name, slug) VALUES (%s, %s)",
            (site, slug)
        )

        logger.info(f"Created site group: {site}")
        return site_group_id

    async def _get_or_create_vlan_group(self, vrf_name: str, site: str) -> int:
        """Get or create VLAN group"""
        vrf_id = await self._get_vrf_id(vrf_name)
        if not vrf_id:
            raise ValueError(f"VRF '{vrf_name}' not found")

        name = f"{vrf_name}-ClickCluster-{site}"
        slug = name.lower().replace('_', '-')

        # Try to get existing
        result = await self._execute_query(
            "SELECT id FROM vlan_groups WHERE slug = %s",
            (slug,),
            fetch_one=True
        )

        if result:
            return result['id']

        # Create new
        vlan_group_id = await self._execute_query(
            "INSERT INTO vlan_groups (name, slug, vrf_id, site) VALUES (%s, %s, %s, %s)",
            (name, slug, vrf_id, site)
        )

        logger.info(f"Created VLAN group: {name}")
        return vlan_group_id

    async def _get_role_id(self) -> int:
        """Get 'Data' role ID"""
        result = await self._execute_query(
            "SELECT id FROM roles WHERE slug = %s",
            ('data',),
            fetch_one=True
        )

        if result:
            return result['id']

        raise ValueError("Data role not found in database")

    # ==================== VLAN Management ====================

    async def _get_or_create_vlan(self, vlan_id: int, epg_name: str, vrf_name: str, site: str) -> int:
        """Get or create VLAN"""
        tenant_id = await self._get_redbull_tenant_id()
        vlan_group_id = await self._get_or_create_vlan_group(vrf_name, site)

        # Check if VLAN exists
        result = await self._execute_query(
            "SELECT id FROM vlans WHERE vlan_id = %s AND vlan_group_id = %s",
            (vlan_id, vlan_group_id),
            fetch_one=True
        )

        if result:
            # Update name if changed
            await self._execute_query(
                "UPDATE vlans SET name = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (epg_name, result['id'])
            )
            return result['id']

        # Create new VLAN
        vlan_db_id = await self._execute_query(
            "INSERT INTO vlans (vlan_id, name, vlan_group_id, tenant_id, status) "
            "VALUES (%s, %s, %s, %s, 'active')",
            (vlan_id, epg_name, vlan_group_id, tenant_id)
        )

        logger.info(f"Created VLAN {vlan_id} ({epg_name}) in group {vlan_group_id}")
        return vlan_db_id

    async def _cleanup_unused_vlan(self, vlan_db_id: int):
        """Delete VLAN if not used by any segment"""
        # Check if any segments use this VLAN
        result = await self._execute_query(
            "SELECT COUNT(*) as count FROM segments WHERE vlan_id = %s",
            (vlan_db_id,),
            fetch_one=True
        )

        if result and result['count'] == 0:
            await self._execute_query(
                "DELETE FROM vlans WHERE id = %s",
                (vlan_db_id,)
            )
            logger.info(f"Cleaned up unused VLAN (id={vlan_db_id})")

    # ==================== Core CRUD Operations ====================

    async def find(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find segments matching query criteria

        Supports:
        - Exact match: {"field": "value"}
        - Regex: {"field": {"$regex": "pattern"}}
        - Not equal: {"field": {"$ne": "value"}}
        - OR conditions: {"$or": [{"field1": "val1"}, {"field2": "val2"}]}
        """
        # Check cache first
        cached = _get_cached("segments")
        if cached is not None:
            logger.info(f"Cache HIT - filtering {len(cached)} segments in memory")
            return self._filter_segments_in_memory(cached, query)

        # Cache miss - fetch from database
        logger.info("Cache MISS - fetching segments from MySQL")

        # Build SQL query
        where_clauses = []
        params = []

        # Always filter by tenant
        tenant_id = await self._get_redbull_tenant_id()
        where_clauses.append("s.tenant_id = %s")
        params.append(tenant_id)

        # Add query filters
        if "$or" not in query:
            where_sql, where_params = self._build_where_clause(query)
            if where_sql:
                where_clauses.append(where_sql)
                params.extend(where_params)

        where_str = " AND ".join(where_clauses) if where_clauses else "1=1"

        sql = f"""
            SELECT
                s.id as _id,
                s.prefix as segment,
                v.name as vrf,
                s.site,
                vlan.vlan_id,
                vlan.name as epg_name,
                s.status,
                s.cluster_name,
                s.dhcp,
                s.comments as description,
                s.allocated_at,
                s.released,
                s.released_at,
                s.created_at,
                s.updated_at
            FROM segments s
            LEFT JOIN vrfs v ON s.vrf_id = v.id
            LEFT JOIN vlans vlan ON s.vlan_id = vlan.id
            WHERE {where_str}
        """

        t_fetch = time.time()
        segments = await self._execute_query(sql, tuple(params), fetch_all=True)
        elapsed = (time.time() - t_fetch) * 1000

        if elapsed > 5000:
            logger.warning(f"⚠️  MYSQL SLOW: fetch segments took {elapsed:.0f}ms")
        else:
            logger.debug(f"⏱️  MYSQL OK: fetch segments took {elapsed:.0f}ms")

        # Convert to list of dicts
        result = [dict(row) for row in segments]

        # Cache the result
        _set_cache("segments", result)

        # Apply $or filter if needed (in-memory)
        if "$or" in query:
            result = self._filter_segments_in_memory(result, query)

        logger.info(f"Found {len(result)} segments")
        return result

    def _build_where_clause(self, query: Dict[str, Any]) -> tuple:
        """Build WHERE clause from query dict"""
        clauses = []
        params = []

        for field, value in query.items():
            if field == "$or":
                continue  # Handle separately

            # Map logical field names to SQL columns
            sql_field = self._map_field_to_sql(field)

            if isinstance(value, dict):
                # Handle operators
                if "$regex" in value:
                    clauses.append(f"{sql_field} REGEXP %s")
                    params.append(value["$regex"])
                elif "$ne" in value:
                    clauses.append(f"({sql_field} != %s OR {sql_field} IS NULL)")
                    params.append(value["$ne"])
            else:
                # Exact match
                clauses.append(f"{sql_field} = %s")
                params.append(value)

        where_str = " AND ".join(clauses) if clauses else ""
        return where_str, params

    def _map_field_to_sql(self, field: str) -> str:
        """Map logical field names to SQL columns"""
        mapping = {
            "_id": "s.id",
            "segment": "s.prefix",
            "vrf": "v.name",
            "site": "s.site",
            "vlan_id": "vlan.vlan_id",
            "epg_name": "vlan.name",
            "status": "s.status",
            "cluster_name": "s.cluster_name",
            "dhcp": "s.dhcp",
            "description": "s.comments",
            "allocated_at": "s.allocated_at",
            "released": "s.released",
            "released_at": "s.released_at",
        }
        return mapping.get(field, f"s.{field}")

    def _filter_segments_in_memory(self, segments: List[Dict], query: Dict[str, Any]) -> List[Dict]:
        """Filter segments in memory (for complex queries and $or)"""
        if not query:
            return segments

        result = []

        for segment in segments:
            if self._matches_query(segment, query):
                result.append(segment)

        return result

    def _matches_query(self, segment: Dict, query: Dict[str, Any]) -> bool:
        """Check if segment matches query"""
        # Handle $or
        if "$or" in query:
            for or_clause in query["$or"]:
                if all(self._field_matches(segment, k, v) for k, v in or_clause.items()):
                    return True
            return False

        # Handle regular fields
        for field, value in query.items():
            if field == "$or":
                continue
            if not self._field_matches(segment, field, value):
                return False

        return True

    def _field_matches(self, segment: Dict, field: str, value: Any) -> bool:
        """Check if field matches value"""
        segment_value = segment.get(field)

        if isinstance(value, dict):
            # Handle operators
            if "$regex" in value:
                if segment_value is None:
                    return False
                return re.search(value["$regex"], str(segment_value)) is not None
            elif "$ne" in value:
                return segment_value != value["$ne"]

        # Exact match
        return segment_value == value

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        results = await self.find(query)
        return results[0] if results else None

    async def find_one_optimized(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Optimized find_one (same as find_one for MySQL)"""
        return await self.find_one(query)

    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert a new segment

        Required fields:
        - segment (IP prefix)
        - vrf (network name)
        - site
        - vlan_id
        - epg_name
        """
        logger.info(f"Creating segment: {document.get('segment')} in VRF {document.get('vrf')} at site {document.get('site')}")

        # Get/create references
        tenant_id = await self._get_redbull_tenant_id()
        vrf_id = await self._get_vrf_id(document['vrf'])
        if not vrf_id:
            raise ValueError(f"VRF '{document['vrf']}' not found")

        role_id = await self._get_role_id()
        site_group_id = await self._get_or_create_site_group(document['site'])

        # Create VLAN
        vlan_db_id = await self._get_or_create_vlan(
            document['vlan_id'],
            document['epg_name'],
            document['vrf'],
            document['site']
        )

        # Insert segment
        segment_id = await self._execute_query(
            """
            INSERT INTO segments
            (prefix, vrf_id, site, site_group_id, vlan_id, tenant_id, role_id,
             status, cluster_name, dhcp, comments, description, allocated_at, released)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                document['segment'],
                vrf_id,
                document['site'],
                site_group_id,
                vlan_db_id,
                tenant_id,
                role_id,
                document.get('status', 'active'),
                document.get('cluster_name'),
                document.get('dhcp'),
                document.get('description'),
                document.get('epg_name'),
                document.get('allocated_at'),
                document.get('released', False)
            )
        )

        # Invalidate cache
        invalidate_cache("segments")

        logger.info(f"Created segment with ID: {segment_id}")

        # Return created segment
        return await self.find_one({"_id": segment_id})

    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Find a segment and update it atomically

        Update format: {"$set": {"field": "value"}}
        """
        # Find segment
        segment = await self.find_one(query)

        if not segment:
            if upsert:
                # Create new segment
                doc = query.copy()
                if "$set" in update:
                    doc.update(update["$set"])
                return await self.insert_one(doc)
            return None

        # Update segment
        segment_id = segment['_id']
        updates = update.get("$set", {})

        logger.info(f"Updating segment {segment_id}: {updates}")

        # Build update query
        set_clauses = []
        params = []

        # Track old VLAN for cleanup
        old_vlan_id = segment.get('vlan_id')
        new_vlan_db_id = None

        for field, value in updates.items():
            if field == "vlan_id" and "epg_name" in updates:
                # Create/update VLAN
                new_vlan_db_id = await self._get_or_create_vlan(
                    value,
                    updates["epg_name"],
                    segment['vrf'],
                    segment['site']
                )
                set_clauses.append("vlan_id = %s")
                params.append(new_vlan_db_id)
                continue

            if field == "epg_name":
                # Handled with vlan_id
                continue

            if field == "description":
                # Map to comments
                set_clauses.append("comments = %s")
                params.append(value)
            elif field == "cluster_name":
                set_clauses.append("cluster_name = %s")
                params.append(value)
                # Update status based on cluster allocation
                if value:
                    set_clauses.append("status = 'reserved'")
                else:
                    set_clauses.append("status = 'active'")
            elif field == "status":
                set_clauses.append("status = %s")
                params.append(value)
            elif field == "dhcp":
                set_clauses.append("dhcp = %s")
                params.append(value)
            elif field == "allocated_at":
                set_clauses.append("allocated_at = %s")
                params.append(value)
            elif field == "released":
                set_clauses.append("released = %s")
                params.append(value)
            elif field == "released_at":
                set_clauses.append("released_at = %s")
                params.append(value)

        if set_clauses:
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            params.append(segment_id)

            sql = f"UPDATE segments SET {', '.join(set_clauses)} WHERE id = %s"

            t_save = time.time()
            await self._execute_query(sql, tuple(params))
            elapsed_save = (time.time() - t_save) * 1000

            if elapsed_save > 2000:
                logger.warning(f"⚠️  MYSQL SLOW: update took {elapsed_save:.0f}ms")
            else:
                logger.debug(f"⏱️  MYSQL OK: update took {elapsed_save:.0f}ms")

        # Cleanup old VLAN if changed
        if new_vlan_db_id and old_vlan_id and new_vlan_db_id != old_vlan_id:
            await self._cleanup_unused_vlan(old_vlan_id)

        # Invalidate cache
        invalidate_cache("segments")

        # Return updated segment
        return await self.find_one({"_id": segment_id})

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment"""
        segment = await self.find_one(query)
        if not segment:
            return False

        segment_id = segment['_id']
        vlan_id = segment.get('vlan_id')

        logger.info(f"Deleting segment {segment_id}")

        # Delete segment
        await self._execute_query(
            "DELETE FROM segments WHERE id = %s",
            (segment_id,)
        )

        # Cleanup VLAN if unused
        if vlan_id:
            await self._cleanup_unused_vlan(vlan_id)

        # Invalidate cache
        invalidate_cache("segments")

        logger.info(f"Deleted segment {segment_id}")
        return True

    # ==================== Utility Methods ====================

    async def get_vrfs(self) -> List[str]:
        """Get list of available VRFs (cached for 1 hour)"""
        cached_vrfs = _get_cached("vrfs")
        if cached_vrfs is not None:
            return cached_vrfs

        t_start = time.time()
        vrfs = await self._execute_query(
            "SELECT name FROM vrfs ORDER BY name",
            fetch_all=True
        )
        elapsed = (time.time() - t_start) * 1000

        if elapsed > 2000:
            logger.warning(f"⚠️  MYSQL SLOW: fetch VRFs took {elapsed:.0f}ms")
        else:
            logger.debug(f"⏱️  MYSQL OK: fetch VRFs took {elapsed:.0f}ms")

        vrf_names = [row['name'] for row in vrfs]
        _set_cache("vrfs", vrf_names)

        return vrf_names

    async def count_documents(self, query: Dict[str, Any]) -> int:
        """Count segments matching query"""
        segments = await self.find(query)
        return len(segments)

    async def close_storage(self):
        """Close database connections"""
        logger.info("Closing MySQL storage connections")
        await close_mysql_pool()


# Factory function for compatibility
def get_storage() -> MySQLStorage:
    """Get MySQL storage instance"""
    return MySQLStorage()
