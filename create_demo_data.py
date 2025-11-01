#!/usr/bin/env python3
"""
Create Multi-Cluster Demo Data in NetBox
=========================================

This script creates comprehensive demo data showing:
- Multiple segments with DHCP/Gateway info in comments
- Various cluster allocations (web, db, app, cache, etc.)
- Mix of Reserved and Active statuses
- Idempotency demonstration
"""

import asyncio
import sys

sys.path.insert(0, '/home/roi/Documents/scripts/segments_2')

from src.models.schemas import Segment, VLANAllocationRequest
from src.services.segment_service import SegmentService
from src.services.allocation_service import AllocationService


async def cleanup_demo_data():
    """Remove any existing demo data"""
    print("🧹 Cleaning up existing demo data...")
    from src.database.netbox_storage import get_storage

    storage = get_storage()
    segments = await storage.find({})

    deleted = 0
    for seg in segments:
        epg = seg.get('epg_name', '')
        if 'DEMO' in epg or 'TEST' in epg:
            await storage.delete_one({'_id': seg['_id']})
            deleted += 1

    print(f"✓ Cleaned up {deleted} existing demo segments\n")


async def create_demo_segments():
    """Create diverse demo segments"""
    print("=" * 90)
    print("CREATING DEMO SEGMENTS")
    print("=" * 90)

    demo_segments = [
        # Production Web Tier
        {
            'site': 'site1',
            'vlan_id': 100,
            'epg_name': 'DEMO_PROD_WEB',
            'segment': '192.168.100.0/24',
            'description': 'DHCP Pool: 192.168.100.10-250 | Gateway: 192.168.100.1 | DNS: 8.8.8.8, 8.8.4.4 | Environment: Production'
        },
        # Production Database Tier
        {
            'site': 'site1',
            'vlan_id': 101,
            'epg_name': 'DEMO_PROD_DB',
            'segment': '192.168.101.0/24',
            'description': 'Static IPs Only | Gateway: 192.168.101.1 | Backup: Daily 2AM | Monitoring: Prometheus'
        },
        # Production Application Tier
        {
            'site': 'site1',
            'vlan_id': 102,
            'epg_name': 'DEMO_PROD_APP',
            'segment': '192.168.102.0/24',
            'description': 'DHCP Pool: 192.168.102.20-200 | Gateway: 192.168.102.1 | Load Balancer: 192.168.102.10'
        },
        # Production Cache Tier
        {
            'site': 'site1',
            'vlan_id': 103,
            'epg_name': 'DEMO_PROD_CACHE',
            'segment': '192.168.103.0/24',
            'description': 'Redis Cluster | Gateway: 192.168.103.1 | Master: 192.168.103.10 | Replicas: .11-.13'
        },
        # DMZ Zone
        {
            'site': 'site1',
            'vlan_id': 104,
            'epg_name': 'DEMO_DMZ',
            'segment': '192.168.104.0/24',
            'description': 'Firewall Zone: DMZ | Gateway: 192.168.104.1 | External Access | Security: High'
        },
        # Staging Environment
        {
            'site': 'site1',
            'vlan_id': 105,
            'epg_name': 'DEMO_STAGING',
            'segment': '192.168.105.0/24',
            'description': 'DHCP Pool: 192.168.105.10-100 | Gateway: 192.168.105.1 | Environment: Staging'
        },
        # Development Environment
        {
            'site': 'site1',
            'vlan_id': 106,
            'epg_name': 'DEMO_DEV',
            'segment': '192.168.106.0/24',
            'description': 'DHCP Enabled | Gateway: 192.168.106.1 | Environment: Development | Access: Internal'
        },
        # Kubernetes Cluster
        {
            'site': 'site1',
            'vlan_id': 107,
            'epg_name': 'DEMO_K8S',
            'segment': '192.168.107.0/24',
            'description': 'Kubernetes Pod Network | Gateway: 192.168.107.1 | CNI: Calico | Service CIDR: 10.96.0.0/12'
        },
        # Site2 - Different IP prefix
        {
            'site': 'site2',
            'vlan_id': 200,
            'epg_name': 'DEMO_SITE2_WEB',
            'segment': '193.168.100.0/24',
            'description': 'Site2 Production Web | Gateway: 193.168.100.1 | Datacenter: DC2'
        },
        # Site2 - Database
        {
            'site': 'site2',
            'vlan_id': 201,
            'epg_name': 'DEMO_SITE2_DB',
            'segment': '193.168.101.0/24',
            'description': 'Site2 Database | Gateway: 193.168.101.1 | Replication: Active-Passive'
        },
    ]

    created = []
    for seg_data in demo_segments:
        try:
            segment = Segment(**seg_data)
            result = await SegmentService.create_segment(segment)
            created.append(seg_data)
            print(f"✓ Created: {seg_data['epg_name']} (VLAN {seg_data['vlan_id']}) - {seg_data['site']}")
        except Exception as e:
            print(f"✗ Failed to create {seg_data['epg_name']}: {e}")

    print(f"\n✓ Created {len(created)}/{len(demo_segments)} demo segments\n")
    return created


async def allocate_to_clusters():
    """Allocate segments to various clusters"""
    print("=" * 90)
    print("ALLOCATING TO CLUSTERS")
    print("=" * 90)

    cluster_allocations = [
        ('site1', 'production-web-cluster-01'),
        ('site1', 'production-web-cluster-01'),  # Idempotency test - should return same VLAN
        ('site1', 'production-database-cluster-02'),
        ('site1', 'production-app-cluster-03'),
        ('site1', 'redis-cache-cluster-04'),
        ('site1', 'dmz-proxy-cluster-05'),
        ('site1', 'staging-cluster-06'),
        ('site2', 'site2-web-cluster-01'),
        ('site2', 'site2-database-cluster-02'),
    ]

    allocated = []
    for site, cluster_name in cluster_allocations:
        try:
            request = VLANAllocationRequest(cluster_name=cluster_name, site=site)
            result = await AllocationService.allocate_vlan(request)
            allocated.append(result)

            print(f"✓ Allocated: {result.epg_name} (VLAN {result.vlan_id}) → {cluster_name}")
            print(f"  Segment: {result.segment}")

        except Exception as e:
            print(f"✗ Failed to allocate to {cluster_name}: {e}")

    print(f"\n✓ Allocated {len(allocated)} VLANs to clusters")

    # Check idempotency
    print("\n🔍 Idempotency Check:")
    idempotent_allocations = [a for a in allocated if a.cluster_name == 'production-web-cluster-01']
    if len(idempotent_allocations) >= 2:
        vlan_ids = [a.vlan_id for a in idempotent_allocations]
        if len(set(vlan_ids)) == 1:
            print(f"✓ Idempotency VERIFIED: production-web-cluster-01 got VLAN {vlan_ids[0]} twice")
        else:
            print(f"✗ Idempotency FAILED: Got different VLANs: {vlan_ids}")

    return allocated


async def show_netbox_summary():
    """Show summary of what's in NetBox"""
    print("\n" + "=" * 90)
    print("NETBOX SUMMARY")
    print("=" * 90)

    from src.database.netbox_storage import get_storage, get_netbox_client

    storage = get_storage()
    nb = get_netbox_client()

    # Get all demo segments
    segments = await storage.find({})
    demo_segments = [s for s in segments if 'DEMO' in s.get('epg_name', '')]

    print(f"\n📊 Total Demo Segments: {len(demo_segments)}")

    # Show by status
    active = [s for s in demo_segments if not s.get('cluster_name') or s.get('released')]
    reserved = [s for s in demo_segments if s.get('cluster_name') and not s.get('released')]

    print(f"   • Active (Available): {len(active)}")
    print(f"   • Reserved (Allocated): {len(reserved)}")

    # Show by site
    site1_segs = [s for s in demo_segments if s.get('site') == 'site1']
    site2_segs = [s for s in demo_segments if s.get('site') == 'site2']

    print(f"\n📍 By Site:")
    print(f"   • site1: {len(site1_segs)} segments")
    print(f"   • site2: {len(site2_segs)} segments")

    # Show allocated clusters
    clusters = set([s.get('cluster_name') for s in reserved if s.get('cluster_name')])
    print(f"\n🖥️  Clusters with Allocations: {len(clusters)}")
    for cluster in sorted(clusters):
        cluster_segs = [s for s in reserved if s.get('cluster_name') == cluster]
        vlan_ids = [s.get('vlan_id') for s in cluster_segs]
        print(f"   • {cluster}: VLAN {vlan_ids[0]}")

    print("\n" + "=" * 90)
    print("VIEW IN NETBOX UI:")
    print("=" * 90)
    print("🌐 https://srcc3192.cloud.netboxapp.com/ipam/prefixes/")
    print("\n✨ What to look for:")
    print("   • STATUS column: Reserved (allocated) or Active (available)")
    print("   • VLAN column: EPG_NAME (VLAN_ID)")
    print("   • DESCRIPTION: Shows 'Cluster: cluster-name' for allocated segments")
    print("   • COMMENTS: Shows DHCP/Gateway/DNS info (user information)")
    print("=" * 90)


async def main():
    """Main execution"""
    print("\n" + "=" * 90)
    print("MULTI-CLUSTER DEMO DATA CREATOR")
    print("=" * 90)
    print("NetBox: https://srcc3192.cloud.netboxapp.com")
    print("=" * 90 + "\n")

    # Cleanup old data
    await cleanup_demo_data()

    # Create segments
    await create_demo_segments()

    # Allocate to clusters
    await allocate_to_clusters()

    # Show summary
    await show_netbox_summary()

    print("\n✅ Demo data creation complete!")
    print("🚀 Now starting the REST API server...\n")


if __name__ == "__main__":
    asyncio.run(main())
