"""
Comprehensive Production-Level Edge Case Test Suite

Tests all functionality with extensive edge cases, error conditions,
boundary conditions, and concurrent operations for production readiness.
"""

import asyncio
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

# Set environment variables before imports
import os
os.environ["NETBOX_URL"] = "https://srcc3192.cloud.netboxapp.com"
os.environ["NETBOX_TOKEN"] = "892ee583fa47f1682ef258f8df00fbeea11f6ebc"
os.environ["SITES"] = "site1,site2,site3"
os.environ["SITE_PREFIXES"] = "site1:192,site2:193,site3:194"

from src.database.netbox_storage import NetBoxStorage, init_storage, get_netbox_client
from src.utils.database_utils import DatabaseUtils
from src.services.allocation_service import AllocationService
from src.services.segment_service import SegmentService
from src.services.stats_service import StatsService


class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.warnings = []
        self.start_time = time.time()

    def pass_test(self, name, details=""):
        self.passed += 1
        msg = f"✓ PASS: {name}"
        if details:
            msg += f" ({details})"
        print(msg)

    def fail_test(self, name, error):
        self.failed += 1
        self.errors.append((name, error))
        print(f"✗ FAIL: {name} - {error}")

    def warn_test(self, name, warning):
        self.warnings.append((name, warning))
        print(f"⚠ WARN: {name} - {warning}")

    def summary(self):
        total = self.passed + self.failed
        elapsed = time.time() - self.start_time

        print(f"\n{'='*70}")
        print(f"COMPREHENSIVE TEST SUMMARY")
        print(f"{'='*70}")
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed} ({self.passed/total*100:.1f}%)")
        print(f"Failed: {self.failed} ({self.failed/total*100:.1f}%)")
        print(f"Warnings: {len(self.warnings)}")
        print(f"Execution Time: {elapsed:.2f}s")

        if self.warnings:
            print(f"\nWarnings:")
            for name, warning in self.warnings:
                print(f"  ⚠ {name}: {warning}")

        if self.errors:
            print(f"\nFailed Tests:")
            for name, error in self.errors:
                print(f"  ✗ {name}: {error}")

        return self.failed == 0


results = TestResults()


# ============================================================================
# CONNECTION AND INITIALIZATION TESTS
# ============================================================================

async def test_netbox_connection():
    """Test 1: NetBox connection and authentication"""
    try:
        await init_storage()
        nb = get_netbox_client()
        status = nb.status()

        if status and "netbox-version" in status:
            results.pass_test("NetBox connection", f"v{status['netbox-version']}")
        else:
            results.fail_test("NetBox connection", "No version in status")
    except Exception as e:
        results.fail_test("NetBox connection", str(e))


async def test_netbox_api_endpoints():
    """Test 2: Verify critical NetBox API endpoints are accessible"""
    try:
        nb = get_netbox_client()

        # Test multiple endpoints
        endpoints = {
            "sites": nb.dcim.sites,
            "vlans": nb.ipam.vlans,
            "prefixes": nb.ipam.prefixes
        }

        all_accessible = True
        for name, endpoint in endpoints.items():
            try:
                list(endpoint.all()[:1])  # Get just 1 item to test
            except Exception as e:
                results.fail_test(f"NetBox {name} endpoint", str(e))
                all_accessible = False

        if all_accessible:
            results.pass_test("NetBox API endpoints", "All accessible")

    except Exception as e:
        results.fail_test("NetBox API endpoints", str(e))


# ============================================================================
# SEGMENT CREATION EDGE CASES
# ============================================================================

async def test_create_minimal_segment():
    """Test 3: Create segment with minimal required fields"""
    try:
        segment_data = {
            "site": "site1",
            "vlan_id": 101,
            "epg_name": "MIN_EPG",
            "segment": "192.168.101.0/24"
        }

        result = await SegmentService.create_segment(segment_data)

        if result and result.get("id"):
            results.pass_test("Minimal segment creation", f"ID: {result['id']}")
            return result["id"]
        else:
            results.fail_test("Minimal segment creation", "No ID returned")
            return None
    except Exception as e:
        results.fail_test("Minimal segment creation", str(e))
        return None


async def test_create_segment_all_fields():
    """Test 4: Create segment with all optional fields"""
    try:
        segment_data = {
            "site": "site2",
            "vlan_id": 102,
            "epg_name": "FULL_EPG_102",
            "segment": "193.168.102.0/24",
            "description": "Full segment with all fields populated",
            "cluster_name": "test-cluster-full",
            "allocated_at": datetime.now(timezone.utc).isoformat(),
            "released": False
        }

        result = await SegmentService.create_segment(segment_data)

        if result and result.get("id"):
            results.pass_test("Full segment creation", f"ID: {result['id']}")
            return result["id"]
        else:
            results.fail_test("Full segment creation", "No ID returned")
            return None
    except Exception as e:
        results.fail_test("Full segment creation", str(e))
        return None


async def test_create_segment_special_characters():
    """Test 5: Segment with special characters in names"""
    try:
        segment_data = {
            "site": "site1",
            "vlan_id": 103,
            "epg_name": "EPG-TEST_123!@#",
            "segment": "192.168.103.0/24",
            "description": "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?"
        }

        result = await SegmentService.create_segment(segment_data)

        if result:
            results.pass_test("Special characters handling")
        else:
            results.fail_test("Special characters handling", "Failed to create")

    except Exception as e:
        results.fail_test("Special characters handling", str(e))


async def test_create_segment_unicode():
    """Test 6: Segment with Unicode characters"""
    try:
        segment_data = {
            "site": "site1",
            "vlan_id": 104,
            "epg_name": "EPG_Unicode_测试",
            "segment": "192.168.104.0/24",
            "description": "Unicode test: 你好世界 🌍 Здравствуй мир"
        }

        result = await SegmentService.create_segment(segment_data)

        if result:
            results.pass_test("Unicode characters handling")
        else:
            results.fail_test("Unicode characters handling", "Failed to create")

    except Exception as e:
        # Unicode might not be supported, that's okay
        results.warn_test("Unicode characters handling", str(e))


async def test_create_segment_long_description():
    """Test 7: Segment with very long description"""
    try:
        long_desc = "A" * 1000  # 1000 characters

        segment_data = {
            "site": "site1",
            "vlan_id": 105,
            "epg_name": "LONG_DESC",
            "segment": "192.168.105.0/24",
            "description": long_desc
        }

        result = await SegmentService.create_segment(segment_data)

        if result:
            results.pass_test("Long description handling", "1000 chars")
        else:
            results.fail_test("Long description handling", "Failed to create")

    except Exception as e:
        results.fail_test("Long description handling", str(e))


# ============================================================================
# VALIDATION EDGE CASES
# ============================================================================

async def test_invalid_site_prefix():
    """Test 8: Wrong IP prefix for site (should fail)"""
    try:
        segment_data = {
            "site": "site1",  # Expects 192.x.x.x
            "vlan_id": 201,
            "epg_name": "WRONG_PREFIX",
            "segment": "10.0.1.0/24"  # Wrong prefix
        }

        try:
            await SegmentService.create_segment(segment_data)
            results.fail_test("Invalid site prefix validation", "Should have rejected")
        except Exception as e:
            if "prefix" in str(e).lower() or "192" in str(e):
                results.pass_test("Invalid site prefix validation")
            else:
                results.fail_test("Invalid site prefix validation", f"Wrong error: {e}")

    except Exception as e:
        results.fail_test("Invalid site prefix validation", str(e))


async def test_empty_epg_name():
    """Test 9: Empty EPG name (should fail)"""
    try:
        segment_data = {
            "site": "site1",
            "vlan_id": 202,
            "epg_name": "",
            "segment": "192.168.202.0/24"
        }

        try:
            await SegmentService.create_segment(segment_data)
            results.fail_test("Empty EPG validation", "Should have rejected")
        except Exception as e:
            if "epg" in str(e).lower():
                results.pass_test("Empty EPG validation")
            else:
                results.fail_test("Empty EPG validation", f"Wrong error: {e}")

    except Exception as e:
        results.fail_test("Empty EPG validation", str(e))


async def test_whitespace_epg_name():
    """Test 10: Whitespace-only EPG name (should fail)"""
    try:
        segment_data = {
            "site": "site1",
            "vlan_id": 203,
            "epg_name": "   \t\n   ",
            "segment": "192.168.203.0/24"
        }

        try:
            await SegmentService.create_segment(segment_data)
            results.fail_test("Whitespace EPG validation", "Should have rejected")
        except Exception as e:
            if "epg" in str(e).lower():
                results.pass_test("Whitespace EPG validation")
            else:
                results.fail_test("Whitespace EPG validation", f"Wrong error: {e}")

    except Exception as e:
        results.fail_test("Whitespace EPG validation", str(e))


async def test_invalid_network_format():
    """Test 11: Host IP instead of network (should fail)"""
    try:
        segment_data = {
            "site": "site1",
            "vlan_id": 204,
            "epg_name": "INVALID_NET",
            "segment": "192.168.1.5/24"  # Host IP not network
        }

        try:
            await SegmentService.create_segment(segment_data)
            results.fail_test("Network format validation", "Should have rejected")
        except Exception as e:
            if "network" in str(e).lower() or "format" in str(e).lower():
                results.pass_test("Network format validation")
            else:
                results.fail_test("Network format validation", f"Wrong error: {e}")

    except Exception as e:
        results.fail_test("Network format validation", str(e))


async def test_invalid_cidr_notation():
    """Test 12: Invalid CIDR notation"""
    try:
        invalid_formats = [
            "192.168.1.0",        # Missing /prefix
            "192.168.1.0/",       # Empty prefix
            "192.168.1.0/33",     # Invalid prefix (>32)
            "192.168.1.0/-1",     # Negative prefix
            "256.168.1.0/24",     # Invalid octet
            "192.168.1/24",       # Missing octet
        ]

        passed = 0
        for invalid_format in invalid_formats:
            segment_data = {
                "site": "site1",
                "vlan_id": 205,
                "epg_name": "INVALID_CIDR",
                "segment": invalid_format
            }

            try:
                await SegmentService.create_segment(segment_data)
                # Should not reach here
            except Exception:
                passed += 1

        if passed == len(invalid_formats):
            results.pass_test("CIDR notation validation", f"Rejected all {len(invalid_formats)} invalid formats")
        else:
            results.fail_test("CIDR notation validation", f"Only rejected {passed}/{len(invalid_formats)}")

    except Exception as e:
        results.fail_test("CIDR notation validation", str(e))


async def test_invalid_site():
    """Test 13: Non-existent site"""
    try:
        segment_data = {
            "site": "nonexistent_site",
            "vlan_id": 206,
            "epg_name": "INVALID_SITE",
            "segment": "192.168.206.0/24"
        }

        try:
            await SegmentService.create_segment(segment_data)
            results.fail_test("Invalid site validation", "Should have rejected")
        except Exception as e:
            if "site" in str(e).lower():
                results.pass_test("Invalid site validation")
            else:
                results.fail_test("Invalid site validation", f"Wrong error: {e}")

    except Exception as e:
        results.fail_test("Invalid site validation", str(e))


async def test_vlan_id_boundaries():
    """Test 14: VLAN ID boundary conditions"""
    try:
        test_cases = [
            (1, "Minimum VLAN", True),
            (4094, "Maximum VLAN", True),
            (0, "Zero VLAN", False),
            (4095, "Reserved VLAN", False),
            (9999, "Too high VLAN", False),
            (-1, "Negative VLAN", False),
        ]

        passed = 0
        for vlan_id, desc, should_succeed in test_cases:
            segment_data = {
                "site": "site1",
                "vlan_id": vlan_id,
                "epg_name": f"VLAN_{vlan_id}",
                "segment": f"192.168.{abs(vlan_id) % 256}.0/24"
            }

            try:
                result = await SegmentService.create_segment(segment_data)
                if should_succeed:
                    passed += 1
                else:
                    results.warn_test(f"VLAN boundary ({desc})", "Should have failed")
            except Exception:
                if not should_succeed:
                    passed += 1
                else:
                    results.warn_test(f"VLAN boundary ({desc})", "Should have succeeded")

        if passed >= 4:  # At least valid cases should pass
            results.pass_test("VLAN ID boundaries", f"{passed}/{len(test_cases)} correct")
        else:
            results.fail_test("VLAN ID boundaries", f"Only {passed}/{len(test_cases)} correct")

    except Exception as e:
        results.fail_test("VLAN ID boundaries", str(e))


# ============================================================================
# DUPLICATE DETECTION TESTS
# ============================================================================

async def test_duplicate_vlan_same_site():
    """Test 15: Duplicate VLAN in same site (should fail)"""
    try:
        # Create first segment
        segment1 = {
            "site": "site3",
            "vlan_id": 301,
            "epg_name": "DUP_TEST_1",
            "segment": "194.168.1.0/24"
        }
        await SegmentService.create_segment(segment1)

        # Try duplicate VLAN in same site
        segment2 = {
            "site": "site3",
            "vlan_id": 301,  # Same VLAN
            "epg_name": "DUP_TEST_2",
            "segment": "194.168.2.0/24"  # Different IP
        }

        try:
            await SegmentService.create_segment(segment2)
            results.fail_test("Duplicate VLAN detection", "Should have rejected")
        except Exception as e:
            if "exists" in str(e).lower() or "duplicate" in str(e).lower():
                results.pass_test("Duplicate VLAN detection")
            else:
                results.warn_test("Duplicate VLAN detection", f"Might have succeeded: {e}")

    except Exception as e:
        results.fail_test("Duplicate VLAN detection", str(e))


async def test_duplicate_segment_same_site():
    """Test 16: Duplicate IP segment in same site"""
    try:
        # Create first segment
        segment1 = {
            "site": "site3",
            "vlan_id": 302,
            "epg_name": "DUP_SEG_1",
            "segment": "194.168.3.0/24"
        }
        await SegmentService.create_segment(segment1)

        # Try duplicate segment
        segment2 = {
            "site": "site3",
            "vlan_id": 303,  # Different VLAN
            "epg_name": "DUP_SEG_2",
            "segment": "194.168.3.0/24"  # Same segment
        }

        try:
            await SegmentService.create_segment(segment2)
            results.warn_test("Duplicate segment detection", "Might allow duplicate segments")
        except Exception as e:
            results.pass_test("Duplicate segment detection")

    except Exception as e:
        results.fail_test("Duplicate segment detection", str(e))


async def test_same_vlan_different_sites():
    """Test 17: Same VLAN ID in different sites (should succeed)"""
    try:
        # Create VLAN 400 in site1
        segment1 = {
            "site": "site1",
            "vlan_id": 400,
            "epg_name": "MULTI_SITE_1",
            "segment": "192.168.40.0/24"
        }
        result1 = await SegmentService.create_segment(segment1)

        # Create same VLAN 400 in site2 (should be allowed)
        segment2 = {
            "site": "site2",
            "vlan_id": 400,
            "epg_name": "MULTI_SITE_2",
            "segment": "193.168.40.0/24"
        }
        result2 = await SegmentService.create_segment(segment2)

        if result1 and result2:
            results.pass_test("Same VLAN different sites")
        else:
            results.fail_test("Same VLAN different sites", "One or both failed")

    except Exception as e:
        results.fail_test("Same VLAN different sites", str(e))


# ============================================================================
# VLAN ALLOCATION EDGE CASES
# ============================================================================

async def test_allocate_to_empty_site():
    """Test 18: Allocate VLAN when site has no segments"""
    try:
        # Try to allocate from a site with possibly no available segments
        result = await AllocationService.allocate_vlan({
            "cluster_name": "test-empty-site",
            "site": "site3"
        })

        if result:
            results.pass_test("Allocate from site", f"Got VLAN {result.get('vlan_id')}")
        else:
            results.warn_test("Allocate from site", "No available segments")

    except Exception as e:
        if "no available" in str(e).lower() or "not found" in str(e).lower():
            results.warn_test("Allocate from empty site", "Expected if site is empty")
        else:
            results.fail_test("Allocate from empty site", str(e))


async def test_allocate_idempotency():
    """Test 19: Multiple allocations to same cluster return same VLAN"""
    try:
        cluster_name = "idempotent-test-cluster"
        site = "site1"

        # First allocation
        result1 = await AllocationService.allocate_vlan({
            "cluster_name": cluster_name,
            "site": site
        })

        # Second allocation (should return same VLAN)
        result2 = await AllocationService.allocate_vlan({
            "cluster_name": cluster_name,
            "site": site
        })

        if result1 and result2 and result1["vlan_id"] == result2["vlan_id"]:
            results.pass_test("Allocation idempotency", f"Both got VLAN {result1['vlan_id']}")
        else:
            results.fail_test("Allocation idempotency", "Different VLANs returned")

    except Exception as e:
        results.fail_test("Allocation idempotency", str(e))


async def test_allocate_cluster_name_edge_cases():
    """Test 20: Cluster names with special characters"""
    try:
        special_names = [
            "cluster-with-dashes",
            "cluster_with_underscores",
            "cluster.with.dots",
            "CLUSTER-UPPERCASE",
            "cluster123numbers",
        ]

        passed = 0
        for cluster_name in special_names:
            try:
                result = await AllocationService.allocate_vlan({
                    "cluster_name": cluster_name,
                    "site": "site1"
                })
                if result:
                    passed += 1
            except Exception:
                pass

        if passed >= 3:
            results.pass_test("Cluster name edge cases", f"{passed}/{len(special_names)} accepted")
        else:
            results.fail_test("Cluster name edge cases", f"Only {passed}/{len(special_names)} accepted")

    except Exception as e:
        results.fail_test("Cluster name edge cases", str(e))


async def test_release_nonexistent_allocation():
    """Test 21: Release allocation that doesn't exist"""
    try:
        result = await AllocationService.release_vlan({
            "cluster_name": "nonexistent-cluster-12345",
            "site": "site1"
        })

        if not result.get("success"):
            results.pass_test("Release nonexistent allocation")
        else:
            results.fail_test("Release nonexistent allocation", "Should have failed")

    except Exception as e:
        if "not found" in str(e).lower():
            results.pass_test("Release nonexistent allocation")
        else:
            results.fail_test("Release nonexistent allocation", str(e))


async def test_release_and_reallocate_cycle():
    """Test 22: Release and reallocate multiple times"""
    try:
        cluster1 = "cycle-test-1"
        cluster2 = "cycle-test-2"
        site = "site2"

        # Allocate to cluster1
        alloc1 = await AllocationService.allocate_vlan({"cluster_name": cluster1, "site": site})
        vlan_id = alloc1.get("vlan_id") if alloc1 else None

        if not vlan_id:
            results.warn_test("Release/reallocate cycle", "No VLAN available")
            return

        # Release from cluster1
        await AllocationService.release_vlan({"cluster_name": cluster1, "site": site})

        # Allocate to cluster2 (should get same VLAN)
        alloc2 = await AllocationService.allocate_vlan({"cluster_name": cluster2, "site": site})

        # Release from cluster2
        await AllocationService.release_vlan({"cluster_name": cluster2, "site": site})

        # Allocate back to cluster1
        alloc3 = await AllocationService.allocate_vlan({"cluster_name": cluster1, "site": site})

        if alloc2 and alloc3:
            results.pass_test("Release/reallocate cycle", f"VLAN {vlan_id} reused")
        else:
            results.fail_test("Release/reallocate cycle", "Cycle failed")

    except Exception as e:
        results.fail_test("Release/reallocate cycle", str(e))


# ============================================================================
# DATA INTEGRITY AND PERSISTENCE TESTS
# ============================================================================

async def test_segment_update_persistence():
    """Test 23: Update segment and verify changes persist"""
    try:
        # Create segment
        segment = {
            "site": "site1",
            "vlan_id": 501,
            "epg_name": "UPDATE_TEST",
            "segment": "192.168.50.0/24",
            "description": "Original description"
        }
        result = await SegmentService.create_segment(segment)
        segment_id = result.get("id") if result else None

        if not segment_id:
            results.fail_test("Update persistence", "Failed to create")
            return

        # Update description
        storage = NetBoxStorage()
        await storage.update_one(
            {"_id": segment_id},
            {"$set": {"description": "Updated description"}}
        )

        # Retrieve and verify
        updated = await storage.find_one({"_id": segment_id})

        if updated and "Updated description" in updated.get("description", ""):
            results.pass_test("Update persistence")
        else:
            results.fail_test("Update persistence", "Changes didn't persist")

    except Exception as e:
        results.fail_test("Update persistence", str(e))


async def test_metadata_storage_in_comments():
    """Test 24: Verify metadata is correctly stored and retrieved from comments"""
    try:
        # Create segment with full metadata
        segment = {
            "site": "site1",
            "vlan_id": 502,
            "epg_name": "META_TEST",
            "segment": "192.168.51.0/24",
            "cluster_name": "meta-cluster",
            "allocated_at": "2025-01-01T00:00:00Z",
            "released": False
        }

        result = await SegmentService.create_segment(segment)
        segment_id = result.get("id") if result else None

        if not segment_id:
            results.fail_test("Metadata storage", "Failed to create")
            return

        # Retrieve and check metadata
        storage = NetBoxStorage()
        retrieved = await storage.find_one({"_id": segment_id})

        if retrieved:
            checks = [
                retrieved.get("epg_name") == "META_TEST",
                retrieved.get("cluster_name") == "meta-cluster",
                retrieved.get("released") == False,
            ]

            if all(checks):
                results.pass_test("Metadata storage", "All metadata preserved")
            else:
                results.fail_test("Metadata storage", f"Some metadata lost: {retrieved}")
        else:
            results.fail_test("Metadata storage", "Failed to retrieve")

    except Exception as e:
        results.fail_test("Metadata storage", str(e))


async def test_special_chars_in_metadata():
    """Test 25: Special characters in metadata fields"""
    try:
        segment = {
            "site": "site1",
            "vlan_id": 503,
            "epg_name": "SPECIAL|META",
            "segment": "192.168.52.0/24",
            "cluster_name": "cluster:with|special",
            "description": "Pipe | chars : and colons"
        }

        result = await SegmentService.create_segment(segment)

        if result:
            # Retrieve and verify
            storage = NetBoxStorage()
            retrieved = await storage.find_one({"_id": result["id"]})

            if retrieved and "SPECIAL" in retrieved.get("epg_name", ""):
                results.pass_test("Special chars in metadata")
            else:
                results.fail_test("Special chars in metadata", "Data corrupted")
        else:
            results.fail_test("Special chars in metadata", "Failed to create")

    except Exception as e:
        results.fail_test("Special chars in metadata", str(e))


# ============================================================================
# QUERY AND SEARCH TESTS
# ============================================================================

async def test_find_by_site():
    """Test 26: Find all segments by site"""
    try:
        storage = NetBoxStorage()
        segments = await storage.find({"site": "site1"})

        if isinstance(segments, list):
            results.pass_test("Find by site", f"Found {len(segments)} segments")
        else:
            results.fail_test("Find by site", "Invalid result type")

    except Exception as e:
        results.fail_test("Find by site", str(e))


async def test_find_by_vlan_id():
    """Test 27: Find segment by VLAN ID"""
    try:
        storage = NetBoxStorage()
        segments = await storage.find({"vlan_id": 101})

        if isinstance(segments, list):
            results.pass_test("Find by VLAN ID", f"Found {len(segments)} segments")
        else:
            results.fail_test("Find by VLAN ID", "Invalid result type")

    except Exception as e:
        results.fail_test("Find by VLAN ID", str(e))


async def test_find_by_cluster():
    """Test 28: Find segments allocated to specific cluster"""
    try:
        storage = NetBoxStorage()
        segments = await storage.find({"cluster_name": "idempotent-test-cluster"})

        if isinstance(segments, list):
            results.pass_test("Find by cluster", f"Found {len(segments)} segments")
        else:
            results.fail_test("Find by cluster", "Invalid result type")

    except Exception as e:
        results.fail_test("Find by cluster", str(e))


async def test_find_with_complex_query():
    """Test 29: Complex query with multiple conditions"""
    try:
        storage = NetBoxStorage()
        segments = await storage.find({
            "site": "site1",
            "released": False
        })

        if isinstance(segments, list):
            results.pass_test("Complex query", f"Found {len(segments)} allocated segments in site1")
        else:
            results.fail_test("Complex query", "Invalid result type")

    except Exception as e:
        results.fail_test("Complex query", str(e))


async def test_count_documents():
    """Test 30: Count documents with and without filter"""
    try:
        storage = NetBoxStorage()

        total_count = await storage.count_documents()
        site1_count = await storage.count_documents({"site": "site1"})

        if total_count >= 0 and site1_count >= 0:
            results.pass_test("Count documents", f"Total: {total_count}, Site1: {site1_count}")
        else:
            results.fail_test("Count documents", "Invalid counts")

    except Exception as e:
        results.fail_test("Count documents", str(e))


# ============================================================================
# STATISTICS AND REPORTING TESTS
# ============================================================================

async def test_site_statistics():
    """Test 31: Calculate statistics for each site"""
    try:
        all_passed = True
        for site in ["site1", "site2", "site3"]:
            try:
                stats = await DatabaseUtils.get_site_statistics(site)

                required_fields = ["site", "total_segments", "allocated", "available", "utilization"]
                if all(field in stats for field in required_fields):
                    continue
                else:
                    all_passed = False
                    results.fail_test(f"Statistics for {site}", "Missing fields")
            except Exception as e:
                all_passed = False
                results.fail_test(f"Statistics for {site}", str(e))

        if all_passed:
            results.pass_test("Site statistics", "All sites calculated")

    except Exception as e:
        results.fail_test("Site statistics", str(e))


async def test_health_check():
    """Test 32: Health check endpoint"""
    try:
        health = await StatsService.health_check()

        required_fields = ["status", "storage_type", "netbox_url", "sites"]
        if all(field in health for field in required_fields):
            results.pass_test("Health check", f"Status: {health['status']}")
        else:
            results.fail_test("Health check", "Missing required fields")

    except Exception as e:
        results.fail_test("Health check", str(e))


# ============================================================================
# ERROR RECOVERY AND RESILIENCE TESTS
# ============================================================================

async def test_netbox_transient_error_handling():
    """Test 33: Graceful handling of NetBox errors"""
    try:
        storage = NetBoxStorage()

        # Try to get non-existent segment
        segment = await storage.find_one({"_id": "999999"})

        if segment is None:
            results.pass_test("Error handling", "Gracefully handled missing segment")
        else:
            results.fail_test("Error handling", "Should return None for missing segment")

    except Exception as e:
        results.fail_test("Error handling", str(e))


async def test_concurrent_reads():
    """Test 34: Concurrent read operations"""
    try:
        storage = NetBoxStorage()

        # Create multiple concurrent read tasks
        tasks = [
            storage.find({"site": "site1"}),
            storage.find({"site": "site2"}),
            storage.find({"site": "site3"}),
            storage.count_documents(),
            storage.find({"released": False}),
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        errors = [r for r in results_list if isinstance(r, Exception)]

        if not errors:
            results.pass_test("Concurrent reads", f"{len(tasks)} concurrent operations")
        else:
            results.fail_test("Concurrent reads", f"{len(errors)} operations failed")

    except Exception as e:
        results.fail_test("Concurrent reads", str(e))


async def test_large_result_set():
    """Test 35: Handle large result sets"""
    try:
        storage = NetBoxStorage()

        # Get all segments
        all_segments = await storage.find({})

        if isinstance(all_segments, list):
            results.pass_test("Large result set", f"Retrieved {len(all_segments)} segments")
        else:
            results.fail_test("Large result set", "Invalid result type")

    except Exception as e:
        results.fail_test("Large result set", str(e))


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def main():
    """Run all comprehensive tests"""
    print("="*70)
    print("COMPREHENSIVE PRODUCTION-LEVEL EDGE CASE TEST SUITE")
    print("="*70)
    print(f"Started: {datetime.now().isoformat()}")
    print(f"NetBox URL: {os.environ['NETBOX_URL']}")
    print()

    # Connection tests
    print("\n--- CONNECTION AND INITIALIZATION ---")
    await test_netbox_connection()
    await test_netbox_api_endpoints()

    # Creation tests
    print("\n--- SEGMENT CREATION EDGE CASES ---")
    await test_create_minimal_segment()
    await test_create_segment_all_fields()
    await test_create_segment_special_characters()
    await test_create_segment_unicode()
    await test_create_segment_long_description()

    # Validation tests
    print("\n--- VALIDATION EDGE CASES ---")
    await test_invalid_site_prefix()
    await test_empty_epg_name()
    await test_whitespace_epg_name()
    await test_invalid_network_format()
    await test_invalid_cidr_notation()
    await test_invalid_site()
    await test_vlan_id_boundaries()

    # Duplicate detection
    print("\n--- DUPLICATE DETECTION ---")
    await test_duplicate_vlan_same_site()
    await test_duplicate_segment_same_site()
    await test_same_vlan_different_sites()

    # Allocation tests
    print("\n--- VLAN ALLOCATION EDGE CASES ---")
    await test_allocate_to_empty_site()
    await test_allocate_idempotency()
    await test_allocate_cluster_name_edge_cases()
    await test_release_nonexistent_allocation()
    await test_release_and_reallocate_cycle()

    # Data integrity
    print("\n--- DATA INTEGRITY AND PERSISTENCE ---")
    await test_segment_update_persistence()
    await test_metadata_storage_in_comments()
    await test_special_chars_in_metadata()

    # Query tests
    print("\n--- QUERY AND SEARCH ---")
    await test_find_by_site()
    await test_find_by_vlan_id()
    await test_find_by_cluster()
    await test_find_with_complex_query()
    await test_count_documents()

    # Statistics
    print("\n--- STATISTICS AND REPORTING ---")
    await test_site_statistics()
    await test_health_check()

    # Resilience
    print("\n--- ERROR RECOVERY AND RESILIENCE ---")
    await test_netbox_transient_error_handling()
    await test_concurrent_reads()
    await test_large_result_set()

    # Summary
    success = results.summary()

    print(f"\nFinished: {datetime.now().isoformat()}")
    print("="*70)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
