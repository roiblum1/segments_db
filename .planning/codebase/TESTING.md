# Testing Patterns

**Analysis Date:** 2026-03-27

## Test Framework

**Runner:**
- pytest
- Config: No explicit pytest.ini found (uses defaults)
- Execution requires running server at `http://localhost:8000` or `http://127.0.0.1:9000/api`

**Assertion Library:**
- pytest assertions (standard `assert` statements)
- requests library for HTTP assertions

**Run Commands:**
```bash
# Run all integration tests (requires server running)
pytest tests/test_api.py -v

# Run quick validation tests
pytest tests/test_api_quick.py -v -s

# Run comprehensive edge case tests (80+ tests)
python test_comprehensive.py

# Run specific test class or method
pytest tests/test_api.py::TestSegmentCRUD::test_create_segment_site1 -v

# Run with detailed output
pytest tests/test_api.py -v --tb=short
```

## Test File Organization

**Location:**
- Tests: `tests/` directory (co-located with src, not nested inside)
- Comprehensive tests: `test_comprehensive.py` at root level
- Test data: `test-data/` directory with JSON test fixtures

**Naming:**
- Test files: `test_*.py` (e.g., `test_api.py`, `test_api_quick.py`)
- Test classes: `Test*` (e.g., `TestHealthCheck`, `TestSegmentCRUD`)
- Test methods: `test_*` (e.g., `test_create_segment_site1`, `test_health_endpoint`)

**Test Files and Purposes:**

1. **`tests/test_api.py`** (1,721 lines)
   - Main integration test suite
   - Covers CRUD operations, validation, edge cases
   - Uses pytest with fixtures for cleanup
   - Base URL: `http://127.0.0.1:9000/api`

2. **`tests/test_api_quick.py`** (208 lines)
   - Quick validation tests for core functionality
   - Validates basic CRUD and constraints
   - Good starting point for validation testing

3. **`tests/test_comprehensive.py`** (788 lines)
   - Comprehensive standalone test suite (not pytest)
   - 80+ edge case tests
   - Tests segment creation, allocation, bulk operations, error handling
   - Can be run directly: `python test_comprehensive.py`
   - Color-coded output with pass/fail statistics

4. **`tests/test_api_integration.py`** (3,588 lines)
   - Extensive integration tests
   - Covers allocation workflows, VLAN release, complex scenarios
   - Long test runs (requires stable server connection)

5. **`tests/test_vlan_allocation.py`** (463 lines)
   - Focused tests for VLAN allocation logic
   - Tests cluster allocation, deallocation, edge cases

6. **`tests/test_netbox_connection.py`** (226 lines)
   - NetBox connectivity tests
   - Validates NetBox configuration and authentication

**Structure:**
```
tests/
├── __init__.py                    # Empty init file
├── test_api.py                    # Main integration tests (pytest)
├── test_api_quick.py              # Quick validation tests (pytest)
├── test_api_integration.py        # Extended integration tests (pytest)
├── test_vlan_allocation.py        # Allocation-specific tests (pytest)
├── test_netbox_connection.py      # NetBox connectivity tests (pytest)
└── test_comprehensive.py          # Comprehensive edge cases (standalone)
```

## Test Structure

**Class-Based Organization:**

```python
class TestHealthCheck:
    """Health check and system status tests"""

    def test_health_endpoint(self):
        """Test health endpoint returns 200 and correct status"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
```

**Fixtures for Setup/Teardown:**

```python
class TestSegmentCRUD:
    """Test Create, Read, Update, Delete operations for segments"""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Cleanup test data before and after each test"""
        # Cleanup before test
        self._cleanup_test_segments()
        yield
        # Cleanup after test
        self._cleanup_test_segments()

    def _cleanup_test_segments(self):
        """Remove any test segments"""
        response = requests.get(f"{BASE_URL}/segments")
        if response.status_code == 200:
            segments = response.json()
            for segment in segments:
                if segment.get("epg_name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/segments/{segment['_id']}")
```

**Patterns:**
- Fixtures with `@pytest.fixture(autouse=True)` for automatic cleanup
- Setup code before `yield`
- Cleanup code after `yield`
- All test segments named with `TEST_` prefix for easy identification

## Standalone Test Suite

**`test_comprehensive.py` Pattern:**

Not pytest-based; uses custom test runner with colored output:

```python
class ComprehensiveTestSuite:
    def __init__(self):
        self.storage = get_storage()
        self.passed = 0
        self.failed = 0
        self.tests = []
        self.created_segments = []  # Track for cleanup

    def log_test(self, name: str, passed: bool, details: str = ""):
        """Log test result with color coding"""
        self.tests.append((name, passed, details))
        if passed:
            print(f"{Colors.GREEN}✓{Colors.RESET} {name}")
            self.passed += 1
        else:
            print(f"{Colors.RED}✗{Colors.RESET} {name}")
            self.failed += 1

    async def test_create_single_segment(self):
        """Test creating a single segment"""
        segment_data = {...}
        result = await self.storage.insert_one(segment_data)
        segment_id = result.get("_id")
        self.created_segments.append(segment_id)

        self.log_test(
            "Create single segment",
            segment_id is not None,
            f"Segment ID: {segment_id}"
        )

    async def cleanup(self):
        """Cleanup created test data"""
        # Release allocated segments
        for segment_id, cluster_name, site in self.allocated_segments:
            try:
                await self.storage.update_one(...)
            except Exception as e:
                print(f"Warning: Failed to release segment {segment_id}: {e}")
```

**Execution:**
```bash
python test_comprehensive.py
```

Outputs colored pass/fail results and final summary.

## Mocking

**Framework:** None explicitly used (relies on server integration)

**Strategy:**
- Integration tests run against real running FastAPI server
- No unit-level mocking for database layer
- Tests interact with actual NetBox via pynetbox client
- Full end-to-end validation of API contracts

**What's Actually Tested:**
- Real HTTP requests to running server
- Real NetBox API calls (via pynetbox)
- Real data persistence
- No mocks = tests are slow but reliable

## Test Data and Fixtures

**Test Data Patterns:**

From `tests/test_api_quick.py`:
```python
segment = {
    "site": "Site1",
    "vlan_id": 1600,
    "epg_name": "TEST_QUICK_ALL_FIELDS",
    "segment": "192.1.160.0/24",
    "vrf": "Network1",
    "dhcp": True,
    "description": "Test all fields"
}
response = requests.post(f"{BASE_URL}/segments", json=segment)
```

**Test Data Cleanup:**

Automatic cleanup using TEST_ prefix:
```python
def cleanup_test_segments(prefix="TEST_"):
    """Helper function to cleanup test segments"""
    try:
        response = requests.get(f"{BASE_URL}/segments", timeout=10)
        if response.status_code == 200:
            segments = response.json()
            for segment in segments:
                if segment.get("epg_name", "").startswith(prefix):
                    requests.delete(f"{BASE_URL}/segments/{segment['id']}", timeout=10)
    except Exception as e:
        print(f"Cleanup error: {e}")
```

**Fixtures Location:**
- `test-data/segments.json` - Test data file
- JSON test data for bulk operations

## Coverage

**Requirements:** Not enforced (no coverage config found)

**View Coverage:**
- No explicit coverage tool configured
- No coverage badges or requirements in tests
- Manual validation through test execution

**Test Count:**
- `test_api.py`: ~1,721 lines (extensive coverage)
- `test_api_integration.py`: ~3,588 lines (very comprehensive)
- `test_comprehensive.py`: ~788 lines (80+ edge case tests)
- Total: ~6,995 lines of test code across all files

## Test Types

**Integration Tests (Primary):**
- HTTP API testing via requests library
- Full workflow testing: create → allocate → release → delete
- Real server at `http://127.0.0.1:9000/api`
- Files: `test_api.py`, `test_api_quick.py`, `test_api_integration.py`

**Scope:**
- Request/response validation
- HTTP status codes
- JSON payload validation
- Error handling
- Business logic workflows

**Example:**
```python
def test_allocate_vlan(self):
    """Test VLAN allocation"""
    allocation = {
        "cluster_name": "test-quick-cluster",
        "site": "Site1",
        "vrf": "Network1"
    }
    response = requests.post(f"{BASE_URL}/allocate-vlan", json=allocation)
    assert response.status_code == 200
    data = response.json()
    assert "vlan_id" in data
    assert "segment" in data
```

**Edge Case Tests:**
- Comprehensive suite in `test_comprehensive.py`
- Tests validation, error conditions, concurrent operations
- Standalone executable for focused testing

**What's NOT Tested:**
- Unit tests for individual functions (no mocking)
- Database layer in isolation
- UI/JavaScript code
- Performance/load testing

## Common Patterns

**Async Testing:**

Comprehensive tests use async/await:
```python
async def test_create_single_segment(self):
    """Test creating a single segment"""
    segment_data = {...}
    result = await self.storage.insert_one(segment_data)
    segment_id = result.get("_id")
    self.log_test("Create single segment", segment_id is not None)
```

Run async tests:
```python
async def run_all_tests(self):
    """Run all tests sequentially"""
    await self.test_create_single_segment()
    await self.test_create_duplicate_vlan_id()
    # ... more tests

# Execute
suite = ComprehensiveTestSuite()
asyncio.run(suite.run_all_tests())
```

**Error Testing:**

From `tests/test_api_quick.py`:
```python
def test_create_segment_missing_vrf_fails(self):
    """Test that VRF is required (Pydantic validation)"""
    segment = {
        "site": "Site1",
        "vlan_id": 1601,
        "epg_name": "TEST_NO_VRF",
        "segment": "192.1.161.0/24",
        # Missing VRF
    }
    response = requests.post(f"{BASE_URL}/segments", json=segment)
    assert response.status_code == 422  # Pydantic validation error
```

Pattern: Send invalid request → verify appropriate HTTP status → verify error message.

**Cache Handling:**

Tests wait for cache to clear between operations:
```python
def test_update_segment_vlan(self):
    """Test updating segment VLAN ID"""
    # Create segment
    create_response = requests.post(f"{BASE_URL}/segments", json=segment)
    segment_id = create_response.json()["id"]

    # Wait for cache (10-minute TTL)
    time.sleep(6)

    # Update VLAN
    response = requests.put(f"{BASE_URL}/segments/{segment_id}", json=segment)
    assert response.status_code == 200

    # Verify update
    time.sleep(6)
    verify_response = requests.get(f"{BASE_URL}/segments/{segment_id}")
    assert verify_response.json()["vlan_id"] == 820
```

Pattern: Create → Wait → Update → Wait → Verify.

**Validation Testing Patterns:**

```python
def test_invalid_site(self):
    """Test site validation"""
    segment = {
        "site": "InvalidSite99",
        "vlan_id": 1602,
        "epg_name": "TEST_INVALID_SITE",
        "segment": "192.1.163.0/24",
        "vrf": "Network1",
        "dhcp": True
    }
    response = requests.post(f"{BASE_URL}/segments", json=segment)
    assert response.status_code in [400, 422]  # Either application or Pydantic validation
```

Validation tests check for appropriate error codes (400 or 422 depending on validation layer).

**Unique Constraints Testing:**

```python
def test_vlan_uniqueness_per_site_and_vrf(self):
    """Test VLAN uniqueness scoped to site + VRF"""
    # Create first segment
    response1 = requests.post(f"{BASE_URL}/segments", json=segment1)
    assert response1.status_code == 200
    id1 = response1.json()["id"]

    time.sleep(3)  # Wait for cache

    # Try duplicate VLAN in same site + VRF (should fail)
    response2 = requests.post(f"{BASE_URL}/segments", json=segment2)
    assert response2.status_code in [400, 422]
```

## Server Requirements

**Test Execution Prerequisites:**
1. Server running: `python main.py` (starts on port 8000 or 9000)
2. NetBox configured and accessible
3. Environment variables set: `NETBOX_URL`, `NETBOX_TOKEN`, `SITES`, `NETWORK_SITE_PREFIXES`
4. Test database/segments cleaned before/after runs

**Startup:**
```bash
# Terminal 1: Start server
python main.py
# Server listens on http://localhost:8000 or http://127.0.0.1:9000/api

# Terminal 2: Run tests
pytest tests/test_api.py -v
```

**Timeout Configuration:**
- Default request timeout: 10 seconds
- Cache invalidation waits: 3-6 seconds
- No explicit pytest timeout configured (can hang on server failures)

## Test Environment

**Configuration:**
- Reads from `.env` file if present
- Uses environment variables: `NETBOX_URL`, `NETBOX_TOKEN`, `SITES`, `NETWORK_SITE_PREFIXES`
- Test segments use `TEST_` prefix for automatic identification and cleanup

**Dependencies:**
- pytest (for pytest-based tests)
- requests (for HTTP testing)
- pynetbox (for NetBox API integration)
- asyncio (for async test support)

---

*Testing analysis: 2026-03-27*
