"""
NetBox Storage Implementation

This module provides a storage interface that uses NetBox's REST API
for managing VLANs and IP prefixes (segments). It replaces the local
JSON file storage with NetBox as the backend.

NetBox Objects Used:
- Sites (dcim.sites): Locations/data centers
- VLANs (ipam.vlans): VLAN definitions
- Prefixes (ipam.prefixes): IP address segments/subnets
- Custom Fields: cluster_name, allocated_at, released, released_at, description

"""

import logging
import pynetbox
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import asyncio

from ..config.settings import NETBOX_URL, NETBOX_TOKEN, NETBOX_SSL_VERIFY

logger = logging.getLogger(__name__)

# Global NetBox API client
_netbox_client: Optional[pynetbox.api] = None


def get_netbox_client() -> pynetbox.api:
    """Get or create the NetBox API client"""
    global _netbox_client

    if _netbox_client is None:
        logger.info(f"Initializing NetBox client: {NETBOX_URL}")
        _netbox_client = pynetbox.api(
            NETBOX_URL,
            token=NETBOX_TOKEN
        )
        _netbox_client.http_session.verify = NETBOX_SSL_VERIFY

    return _netbox_client


async def init_storage():
    """Initialize NetBox storage - verify connection"""
    try:
        nb = get_netbox_client()

        # Test connection by getting status
        loop = asyncio.get_event_loop()
        status = await loop.run_in_executor(None, lambda: nb.status())

        logger.info(f"NetBox connection successful - Version: {status.get('netbox-version')}")
        logger.info(f"NetBox URL: {NETBOX_URL}")

    except Exception as e:
        logger.error(f"Failed to connect to NetBox: {e}")
        raise


async def close_storage():
    """Close NetBox storage - cleanup if needed"""
    global _netbox_client

    if _netbox_client is not None:
        logger.info("Closing NetBox client connection")
        # pynetbox doesn't require explicit close
        _netbox_client = None


class NetBoxStorage:
    """
    NetBox Storage Implementation

    Maps our segment/VLAN data model to NetBox's IPAM model:
    - Segment = NetBox Prefix (IP subnet)
    - VLAN ID = NetBox VLAN
    - Site = NetBox Site
    - EPG Name = Stored in Prefix description/custom field
    - Cluster allocation = Custom field on Prefix
    """

    def __init__(self):
        self.nb = get_netbox_client()

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single segment matching the query"""
        results = await self.find(query)
        return results[0] if results else None

    async def find(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Find segments matching the query

        Query examples:
        - {"site": "site1"} - All segments for site1
        - {"cluster_name": "cluster1", "released": False} - Allocated to cluster1
        - {"vlan_id": 100} - VLAN 100
        """
        loop = asyncio.get_event_loop()

        # Build NetBox filter
        nb_filter = {}

        if query:
            if "site" in query:
                nb_filter["site"] = query["site"]
            if "vlan_id" in query:
                nb_filter["vlan_vid"] = query["vlan_id"]
            # For complex queries, we'll filter in-memory after fetching

        # Fetch prefixes from NetBox
        prefixes = await loop.run_in_executor(
            None,
            lambda: list(self.nb.ipam.prefixes.filter(**nb_filter))
        )

        # Convert NetBox prefixes to our segment format
        segments = []
        for prefix in prefixes:
            segment = self._prefix_to_segment(prefix)

            # Apply additional in-memory filters
            if query:
                if "cluster_name" in query and segment.get("cluster_name") != query["cluster_name"]:
                    continue
                if "released" in query and segment.get("released") != query["released"]:
                    continue
                if "$or" in query:
                    # Handle $or queries
                    match = False
                    for or_condition in query["$or"]:
                        if all(segment.get(k) == v for k, v in or_condition.items()):
                            match = True
                            break
                    if not match:
                        continue

            segments.append(segment)

        return segments

    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new segment in NetBox"""
        loop = asyncio.get_event_loop()

        try:
            # Prepare prefix data
            prefix_data = {
                "prefix": document["segment"],
                "description": document.get("description", ""),
                "status": "active",
            }

            # Add site if provided
            if "site" in document:
                site_obj = await self._get_or_create_site(document["site"])
                prefix_data["site"] = site_obj.id

            # Add VLAN if provided
            if "vlan_id" in document:
                vlan_obj = await self._get_or_create_vlan(
                    document["vlan_id"],
                    document.get("epg_name", f"VLAN_{document['vlan_id']}"),
                    document.get("site")
                )
                prefix_data["vlan"] = vlan_obj.id

            # Add custom fields for our metadata
            prefix_data["custom_fields"] = {
                "epg_name": document.get("epg_name", ""),
                "cluster_name": document.get("cluster_name"),
                "allocated_at": document.get("allocated_at"),
                "released": document.get("released", False),
                "released_at": document.get("released_at"),
            }

            # Create prefix in NetBox
            prefix = await loop.run_in_executor(
                None,
                lambda: self.nb.ipam.prefixes.create(**prefix_data)
            )

            logger.info(f"Created prefix in NetBox: {prefix.prefix} (ID: {prefix.id})")

            # Return in our format
            return self._prefix_to_segment(prefix)

        except Exception as e:
            logger.error(f"Error creating prefix in NetBox: {e}")
            raise

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a segment in NetBox"""
        loop = asyncio.get_event_loop()

        # Find the prefix
        segment = await self.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]
            prefix = await loop.run_in_executor(
                None,
                lambda: self.nb.ipam.prefixes.get(prefix_id)
            )

            # Apply updates
            if "$set" in update:
                updates = update["$set"]

                # Update basic fields
                if "description" in updates:
                    prefix.description = updates["description"]

                # Update custom fields
                if not hasattr(prefix, 'custom_fields'):
                    prefix.custom_fields = {}

                for field in ["cluster_name", "allocated_at", "released", "released_at"]:
                    if field in updates:
                        prefix.custom_fields[field] = updates[field]

                # Save changes
                await loop.run_in_executor(None, prefix.save)
                logger.info(f"Updated prefix {prefix.prefix} (ID: {prefix_id})")

            return True

        except Exception as e:
            logger.error(f"Error updating prefix in NetBox: {e}")
            return False

    async def delete_one(self, query: Dict[str, Any]) -> bool:
        """Delete a segment from NetBox"""
        loop = asyncio.get_event_loop()

        segment = await self.find_one(query)
        if not segment:
            return False

        try:
            prefix_id = segment["_id"]
            await loop.run_in_executor(
                None,
                lambda: self.nb.ipam.prefixes.get(prefix_id).delete()
            )
            logger.info(f"Deleted prefix ID: {prefix_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting prefix from NetBox: {e}")
            return False

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        """Count segments matching the query"""
        results = await self.find(query or {})
        return len(results)

    async def find_one_and_update(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find and update a segment atomically"""
        segment = await self.find_one(query)
        if segment:
            await self.update_one(query, update)
            # Return updated segment
            return await self.find_one(query)
        return None

    def _prefix_to_segment(self, prefix) -> Dict[str, Any]:
        """Convert NetBox prefix object to our segment format"""
        # Get custom fields safely
        custom_fields = getattr(prefix, 'custom_fields', {}) or {}

        segment = {
            "_id": str(prefix.id),
            "site": prefix.site.slug if prefix.site else None,
            "vlan_id": prefix.vlan.vid if prefix.vlan else None,
            "epg_name": custom_fields.get("epg_name", ""),
            "segment": str(prefix.prefix),
            "description": prefix.description or "",
            "cluster_name": custom_fields.get("cluster_name"),
            "allocated_at": custom_fields.get("allocated_at"),
            "released": custom_fields.get("released", False),
            "released_at": custom_fields.get("released_at"),
        }

        return segment

    async def _get_or_create_site(self, site_slug: str):
        """Get or create a site in NetBox"""
        loop = asyncio.get_event_loop()

        # Try to get existing site
        site = await loop.run_in_executor(
            None,
            lambda: self.nb.dcim.sites.get(slug=site_slug)
        )

        if not site:
            # Create new site
            site = await loop.run_in_executor(
                None,
                lambda: self.nb.dcim.sites.create(
                    name=site_slug.upper(),
                    slug=site_slug,
                    status="active"
                )
            )
            logger.info(f"Created site in NetBox: {site_slug}")

        return site

    async def _get_or_create_vlan(self, vlan_id: int, name: str, site_slug: Optional[str] = None):
        """Get or create a VLAN in NetBox"""
        loop = asyncio.get_event_loop()

        # Build filter
        vlan_filter = {"vid": vlan_id}
        if site_slug:
            vlan_filter["site"] = site_slug

        # Try to get existing VLAN
        vlan = await loop.run_in_executor(
            None,
            lambda: self.nb.ipam.vlans.get(**vlan_filter)
        )

        if not vlan:
            # Prepare VLAN data
            vlan_data = {
                "vid": vlan_id,
                "name": name,
                "status": "active",
            }

            if site_slug:
                site = await self._get_or_create_site(site_slug)
                vlan_data["site"] = site.id

            # Create new VLAN
            vlan = await loop.run_in_executor(
                None,
                lambda: self.nb.ipam.vlans.create(**vlan_data)
            )
            logger.info(f"Created VLAN in NetBox: {vlan_id} ({name})")

        return vlan


def get_storage() -> NetBoxStorage:
    """Get the NetBox storage instance"""
    return NetBoxStorage()
