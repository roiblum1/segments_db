#!/usr/bin/env python3
"""
Script to create required NetBox resources for VLAN Manager

Creates:
- RedBull tenant
- Data role (for prefixes and VLANs)
- Site groups: Site1, Site2, Site3
- VRFs: Network1, Network2, Network3
- Custom fields: DHCP, Cluster (for IP Prefixes)

Usage:
    export NETBOX_URL="https://your-netbox-instance.com"
    export NETBOX_TOKEN="your-api-token"
    python3 create_netbox_resources.py
"""

import sys
import os
import logging
import re
from typing import Optional, Any

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

try:
    import pynetbox
except ImportError:
    print("ERROR: pynetbox is not installed!")
    print("Install it with: pip install pynetbox")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def sanitize_slug(text: str) -> str:
    """Convert text to a valid NetBox slug"""
    slug = text.lower()
    slug = slug.replace(" ", "-").replace("_", "-")
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


def create_tenant(nb: pynetbox.api, name: str, slug: str) -> Optional[object]:
    """Create a tenant in NetBox if it doesn't exist"""
    try:
        # Check if tenant already exists
        existing = nb.tenancy.tenants.get(slug=slug)
        
        if existing:
            logger.info(f"✅ Tenant '{name}' already exists (ID: {existing.id})")
            return existing
        
        # Create tenant
        logger.info(f"Creating tenant '{name}'...")
        tenant_data = {
            "name": name,
            "slug": slug,
        }
        
        tenant = nb.tenancy.tenants.create(**tenant_data)
        logger.info(f"✅ Created tenant '{name}' (ID: {tenant.id})")
        return tenant
        
    except Exception as e:
        logger.error(f"❌ Error creating tenant '{name}': {e}")
        return None


def create_role(nb: pynetbox.api, name: str) -> Optional[object]:
    """Create a role in NetBox if it doesn't exist"""
    try:
        # Check if role already exists
        existing = nb.ipam.roles.get(name=name)
        
        if existing:
            logger.info(f"✅ Role '{name}' already exists (ID: {existing.id})")
            return existing
        
        # Create role
        logger.info(f"Creating role '{name}'...")
        role_data = {
            "name": name,
            "slug": sanitize_slug(name),
        }
        
        role = nb.ipam.roles.create(**role_data)
        logger.info(f"✅ Created role '{name}' (ID: {role.id})")
        return role
        
    except Exception as e:
        logger.error(f"❌ Error creating role '{name}': {e}")
        return None


def create_site_group(nb: pynetbox.api, name: str, slug: Optional[str] = None) -> Optional[object]:
    """Create a site group in NetBox if it doesn't exist
    
    Args:
        nb: NetBox API client
        name: Site group name (can be capitalized, e.g., "Site1")
        slug: Optional slug (auto-generated from name if not provided, normalized to lowercase)
    
    Note: NetBox requires slugs to be lowercase, but names can be capitalized.
    The production code normalizes user input to lowercase for slug lookups.
    """
    try:
        # Auto-generate slug from name if not provided (normalize to lowercase)
        if slug is None:
            slug = sanitize_slug(name)
            logger.debug(f"Auto-generated slug '{slug}' from name '{name}'")
        
        # Ensure slug is lowercase (NetBox requirement)
        slug = slug.lower()
        
        # Check if site group already exists
        existing = nb.dcim.site_groups.get(slug=slug)
        
        if existing:
            logger.info(f"✅ Site group '{name}' (slug: '{slug}') already exists (ID: {existing.id})")
            return existing
        
        # Create site group
        logger.info(f"Creating site group '{name}' with slug '{slug}'...")
        site_group_data = {
            "name": name,
            "slug": slug,
        }
        
        site_group = nb.dcim.site_groups.create(**site_group_data)
        logger.info(f"✅ Created site group '{name}' (slug: '{slug}', ID: {site_group.id})")
        return site_group
        
    except Exception as e:
        logger.error(f"❌ Error creating site group '{name}': {e}")
        return None


def create_custom_field(nb: pynetbox.api, name: str, field_type: str = "text", object_types: list = None, required: bool = False, default: Any = None) -> Optional[object]:
    """Create a custom field in NetBox if it doesn't exist
    
    Args:
        nb: NetBox API client
        name: Custom field name
        field_type: Field type (text, boolean, integer, etc.)
        object_types: List of object types this field applies to (e.g., ['ipam.prefix'])
        required: Whether field is required
        default: Default value
    """
    try:
        # Check if custom field already exists
        existing = nb.extras.custom_fields.get(name=name)
        
        if existing:
            logger.info(f"✅ Custom field '{name}' already exists (ID: {existing.id})")
            return existing
        
        # Create custom field
        logger.info(f"Creating custom field '{name}' (type: {field_type})...")
        field_data = {
            "name": name,
            "type": field_type,
            "label": name,
        }
        
        # NetBox API requires 'object_types' (not 'content_types')
        if object_types:
            field_data["object_types"] = object_types
        
        if required:
            field_data["required"] = required
        
        if default is not None:
            field_data["default"] = default
        
        custom_field = nb.extras.custom_fields.create(**field_data)
        logger.info(f"✅ Created custom field '{name}' (ID: {custom_field.id})")
        return custom_field
        
    except Exception as e:
        logger.error(f"❌ Error creating custom field '{name}': {e}")
        return None


def create_vrf(nb: pynetbox.api, name: str, tenant_id: Optional[int] = None) -> Optional[object]:
    """Create a VRF in NetBox if it doesn't exist"""
    try:
        # Check if VRF already exists
        existing = nb.ipam.vrfs.get(name=name)
        
        if existing:
            logger.info(f"✅ VRF '{name}' already exists (ID: {existing.id})")
            return existing
        
        # Create VRF
        logger.info(f"Creating VRF '{name}'...")
        vrf_data = {
            "name": name,
        }
        
        # Assign tenant if provided
        if tenant_id:
            vrf_data["tenant"] = tenant_id
            logger.debug(f"Assigning tenant ID {tenant_id} to VRF '{name}'")
        
        vrf = nb.ipam.vrfs.create(**vrf_data)
        logger.info(f"✅ Created VRF '{name}' (ID: {vrf.id})")
        return vrf
        
    except Exception as e:
        logger.error(f"❌ Error creating VRF '{name}': {e}")
        return None


def main():
    """Create all required NetBox resources"""
    logger.info("🚀 Starting NetBox resource creation...")
    
    # Check environment variables
    netbox_url = os.getenv('NETBOX_URL')
    netbox_token = os.getenv('NETBOX_TOKEN')
    netbox_ssl_verify = os.getenv('NETBOX_SSL_VERIFY', 'true').lower() in ('true', '1', 'yes')
    
    if not netbox_url:
        logger.error("❌ NETBOX_URL environment variable is not set!")
        logger.error("   Set it with: export NETBOX_URL='https://your-netbox-instance.com'")
        sys.exit(1)
    
    if not netbox_token:
        logger.error("❌ NETBOX_TOKEN environment variable is not set!")
        logger.error("   Set it with: export NETBOX_TOKEN='your-api-token'")
        sys.exit(1)
    
    logger.info(f"NetBox URL: {netbox_url}")
    logger.info(f"SSL Verify: {netbox_ssl_verify}")
    
    # Initialize NetBox client
    try:
        nb = pynetbox.api(netbox_url, token=netbox_token)
        nb.http_session.verify = netbox_ssl_verify
        
        # Test connection
        logger.info("Testing NetBox connection...")
        nb.tenancy.tenants.all()
        logger.info("✅ Connected to NetBox successfully")
    except Exception as e:
        logger.error(f"❌ Failed to connect to NetBox: {e}")
        sys.exit(1)
    
    results = {
        "tenant": False,
        "role": False,
        "site_groups": [],
        "vrfs": [],
        "custom_fields": []
    }
    
    # 1. Create RedBull tenant (needed for VRFs)
    logger.info("\n" + "="*60)
    logger.info("Creating Tenant: RedBull")
    logger.info("="*60)
    tenant = create_tenant(nb, "RedBull", "redbull")
    results["tenant"] = tenant is not None
    tenant_id = tenant.id if tenant else None
    
    # 2. Create Data role
    logger.info("\n" + "="*60)
    logger.info("Creating Role: Data")
    logger.info("="*60)
    role = create_role(nb, "Data")
    results["role"] = role is not None
    
    # 3. Create site groups
    logger.info("\n" + "="*60)
    logger.info("Creating Site Groups: Site1, Site2, Site3")
    logger.info("="*60)
    # Note: Names can be capitalized, but slugs will be auto-generated as lowercase
    # This matches NetBox requirements and production code normalization
    site_group_names = ["Site1", "Site2", "Site3"]
    
    for name in site_group_names:
        # Slug will be auto-generated as lowercase (e.g., "Site1" -> "site1")
        site_group = create_site_group(nb, name)
        results["site_groups"].append(site_group is not None)
    
    # 4. Create VRFs
    logger.info("\n" + "="*60)
    logger.info("Creating VRFs: Network1, Network2, Network3")
    logger.info("="*60)
    vrf_names = ["Network1", "Network2", "Network3"]
    
    for vrf_name in vrf_names:
        vrf = create_vrf(nb, vrf_name, tenant_id)
        results["vrfs"].append(vrf is not None)
    
    # 5. Create custom fields for IP Prefixes
    logger.info("\n" + "="*60)
    logger.info("Creating Custom Fields: DHCP, Cluster")
    logger.info("="*60)
    
    # DHCP custom field (boolean)
    dhcp_field = create_custom_field(
        nb,
        name="DHCP",
        field_type="boolean",
        object_types=["ipam.prefix"],
        required=False,
        default=False
    )
    results["custom_fields"].append(dhcp_field is not None)
    
    # Cluster custom field (text)
    cluster_field = create_custom_field(
        nb,
        name="Cluster",
        field_type="text",
        object_types=["ipam.prefix"],
        required=False,
        default=None
    )
    results["custom_fields"].append(cluster_field is not None)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("📊 Summary")
    logger.info("="*60)
    logger.info(f"Tenant (RedBull): {'✅' if results['tenant'] else '❌'}")
    logger.info(f"Role (Data): {'✅' if results['role'] else '❌'}")
    logger.info(f"Site Groups: {sum(results['site_groups'])}/3 created")
    logger.info(f"VRFs: {sum(results['vrfs'])}/3 created")
    logger.info(f"Custom Fields: {sum(results['custom_fields'])}/2 created")
    
    # Check if all succeeded
    all_success = (
        results["tenant"] and
        results["role"] and
        all(results["site_groups"]) and
        all(results["vrfs"]) and
        all(results["custom_fields"])
    )
    
    if all_success:
        logger.info("\n✅ All resources created successfully!")
        sys.exit(0)
    else:
        logger.error("\n❌ Some resources failed to create. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
