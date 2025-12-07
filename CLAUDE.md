# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**VLAN Manager** is a production-grade network VLAN allocation and management system that provides an intelligent API layer on top of NetBox IPAM. It automates VLAN segment allocation for clusters across multiple sites with VRF support, comprehensive validation, and a modern web interface.

**Type**: FastAPI Web Application + REST API
**Primary Language**: Python 3.11
**Architecture Pattern**: Clean Architecture with service-oriented design
**Storage Backend**: NetBox IPAM (PostgreSQL backend via pynetbox)
**Deployment**: Containerized (Podman/Docker), Kubernetes/OpenShift ready

---

## Development Commands

### Local Development Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with NetBox credentials and site configuration

# 4. Run application directly
python main.py
# Server starts on http://localhost:8000
```

### Testing

```bash
# Run integration tests (requires running server at http://localhost:8000)
pytest tests/test_api.py -v

# Run comprehensive validation tests (80+ edge case tests)
python test_comprehensive.py

# Run with detailed output
pytest tests/test_api.py -v --tb=short

# Run specific test
pytest tests/test_api.py::TestClass::test_method -v
```

### Container Deployment (Podman)

```bash
# Full deployment (build + start)
./run.sh deploy

# Individual commands
./run.sh build          # Build image only
./run.sh start          # Start container
./run.sh stop           # Stop container
./run.sh restart        # Restart container
./run.sh logs           # Show and follow logs
./run.sh status         # Show container status
./run.sh test           # Run tests
./run.sh clean          # Remove container and volume
```

**Note**: The project uses Podman, not Docker. All scripts use `podman` commands.

### Manual Container Deployment

```bash
# Build
podman build -t vlan-manager:latest .

# Run
podman run -d \
  --name vlan-manager \
  -p 8000:8000 \
  --env-file .env \
  -v vlan-data:/app/data \
  vlan-manager:latest

# View logs
podman logs -f vlan-manager

# Stop
podman stop vlan-manager
```

---

## Architecture Overview

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                      VLAN Manager                           │
│  (Intelligent API Layer + Business Logic + Validation)     │
└─────────────────────────┬───────────────────────────────────┘
                          │ pynetbox
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    NetBox IPAM                              │
│  (Persistent Storage + REST API + PostgreSQL Backend)      │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **NetBox as Backend**: Uses NetBox's professional IPAM system via pynetbox library
   - Provides PostgreSQL scalability and reliability
   - Professional UI for network administrators
   - Audit trails and change logging
   - Multi-user support with RBAC

2. **Clean Architecture**: Separation of concerns with distinct layers
   - API Layer (`src/api/routes.py`)
   - Service Layer (`src/services/`)
   - Database Layer (`src/database/` - refactored into focused modules)
   - Models (`src/models/schemas.py`)
   - Utilities (`src/utils/`)

3. **Async/Await Pattern**: Fully asynchronous for performance
   - Thread pool executors for NetBox I/O operations
   - Separate pools for read (30 workers) vs write (20 workers) operations
   - Request coalescing to prevent duplicate API calls

4. **Aggressive Caching**: 10-minute cache for NetBox queries
   - Reduces API calls to NetBox Cloud (which throttles heavily)
   - In-flight request tracking prevents concurrent duplicate fetches
   - Cache invalidation on write operations

5. **Modular Database Layer**: NetBox integration split into focused modules (1,560 total lines)
   - `netbox_storage.py`: Main storage interface & initialization (~200 lines)
   - `netbox_crud_ops.py`: Create/Update/Delete operations (~344 lines)
   - `netbox_query_ops.py`: Read/query operations (~198 lines)
   - `netbox_helpers.py`: NetBox object helpers - VRF, VLAN, Tenant, Role, Site (~360 lines)
   - `netbox_client.py`: Client initialization and thread pool executors (~139 lines)
   - `netbox_cache.py`: TTL-based cache management with request coalescing (~101 lines)
   - `netbox_utils.py`: Utility functions - safe access, conversion (~145 lines)
   - `netbox_constants.py`: Centralized constants to eliminate magic strings (~57 lines)

---

## Directory Structure

```
segments_2/
├── main.py                 # Entry point (delegates to src/run.py)
├── requirements.txt        # Python dependencies (8 packages)
├── Dockerfile             # Container image definition
├── .env.example           # Environment configuration template
├── README.md              # User documentation
├── run.sh                 # Podman deployment script
│
├── src/                   # Application source code
│   ├── run.py            # Server startup (uvicorn)
│   ├── app.py            # FastAPI application setup, lifespan, middleware
│   │
│   ├── api/              # REST API endpoints
│   │   └── routes.py     # All API routes
│   │
│   ├── config/           # Configuration and settings
│   │   └── settings.py   # Environment variables, validation, logging
│   │
│   ├── database/         # NetBox storage integration (REFACTORED - 1,560 lines)
│   │   ├── __init__.py              # Public API exports (16 lines)
│   │   ├── netbox_storage.py       # Main storage interface (200 lines)
│   │   ├── netbox_crud_ops.py      # Create/Update/Delete ops (344 lines)
│   │   ├── netbox_query_ops.py     # Read/query operations (198 lines)
│   │   ├── netbox_helpers.py       # NetBox object helpers (360 lines)
│   │   ├── netbox_client.py        # Client and executors (139 lines)
│   │   ├── netbox_cache.py         # TTL-based caching (101 lines)
│   │   ├── netbox_utils.py         # Utility functions (145 lines)
│   │   └── netbox_constants.py     # Centralized constants (57 lines)
│   │
│   ├── models/           # Data models
│   │   └── schemas.py    # Pydantic models (Segment, VLANAllocation, etc.)
│   │
│   ├── services/         # Business logic layer
│   │   ├── allocation_service.py   # VLAN allocation logic
│   │   ├── segment_service.py      # Segment CRUD operations
│   │   ├── stats_service.py        # Statistics and health checks
│   │   ├── export_service.py       # CSV/Excel export
│   │   └── logs_service.py         # Log file access
│   │
│   └── utils/            # Utility functions
│       ├── validators.py        # Comprehensive validation (~700+ lines)
│       ├── database_utils.py    # Database operation helpers
│       ├── error_handlers.py    # Retry logic, error translation
│       └── time_utils.py        # Timezone utilities
│
├── static/               # Web UI (served by FastAPI)
│   ├── html/
│   │   ├── index.html   # Main dashboard
│   │   └── help.html    # Help documentation
│   ├── css/
│   │   └── styles.css   # Dark/light theme support
│   └── js/
│       └── app.js       # Frontend JavaScript
│
├── tests/                # Test suite
│   ├── __init__.py
│   └── test_api.py      # Integration tests (pytest)
│
├── test_comprehensive.py # Comprehensive validation tests (80+ tests)
│
└── deploy/               # Deployment configurations
    ├── helm/            # Kubernetes Helm chart
    └── scripts/         # Deployment scripts
```

**Total Database Layer**: 1,560 lines across 9 focused modules (down from ~1,780-1,800 after recent simplifications)

---

## Critical Configuration

### Required Environment Variables

```bash
# NetBox Connection (CRITICAL)
NETBOX_URL="https://your-netbox-instance.com"
NETBOX_TOKEN="your-api-token-here"

# Site Configuration (CRITICAL)
SITES="site1,site2,site3"  # Comma-separated site names

# Site IP Prefix Validation (CRITICAL)
SITE_PREFIXES="site1:192,site2:193,site3:194"
# Format: site1:first_octet,site2:first_octet
# MUST include all sites or app will fail at startup
```

### Startup Validation (CRITICAL)

The application performs **fail-fast validation** at startup:
- ✅ Validates that every site in `SITES` has a corresponding entry in `SITE_PREFIXES`
- ❌ Crashes immediately with clear error message if configuration is incomplete
- ✅ Prevents runtime issues from configuration errors

**Example Error**:
```
CRITICAL CONFIGURATION ERROR: Sites ['site4'] are missing IP prefixes!
Configured sites: ['site1', 'site2', 'site3', 'site4']
Available prefixes: {'site1': '192', 'site2': '193', 'site3': '194'}
Please add missing prefixes to SITE_PREFIXES environment variable.
```

---

## NetBox Data Mapping

Understanding how VLAN Manager concepts map to NetBox objects:

| VLAN Manager Concept | NetBox Object | Notes |
|---------------------|---------------|-------|
| Segment | IP Prefix | Network subnet (e.g., 192.168.1.0/24) |
| VLAN ID | VLAN | VLAN with VID (1-4094) |
| Site | Site Group | Scope for prefixes |
| EPG Name | VLAN Name | Network endpoint group name |
| Cluster Allocation | Custom Field "cluster" | Which cluster is using this segment |
| VRF | VRF | Virtual routing and forwarding instance |
| DHCP | Custom Field "dhcp" | DHCP enabled/disabled |
| Description | Comments | User notes |
| Allocation Status | Prefix Status | "active" = available, "reserved" = allocated |

### NetBox Object Hierarchy

```
Tenant (Redbull)
    ├── VRFs (Network1, Network2, Network3)
    ├── Site Groups (site1, site2, site3)
    ├── VLAN Groups (Network1-ClickCluster-Site1, etc.)
    ├── VLANs (with tenant, role "Data", VLAN group)
    │   └── Prefixes (scope: Site Group, VRF, VLAN, role "Data")
    │       ├── Custom Fields:
    │       │   ├── cluster (allocation)
    │       │   └── dhcp (enabled/disabled)
    │       └── Status: "active" (available) or "reserved" (allocated)
```

---

## Request Flow Example

### Allocating a VLAN

```
HTTP POST /api/allocate-vlan
    ↓
routes.py → allocation_service.py
    ↓
AllocationService.allocate_vlan()
    ├─ validators.py: Validate site, cluster_name, VRF
    ├─ database_utils.py: Check existing allocation
    └─ database_utils.py: Find and allocate segment (atomic)
        ↓
    netbox_storage.py → NetBox REST API
        ├─ Find available segment (filter by site, VRF, unallocated)
        ├─ Update prefix status to "reserved"
        ├─ Set custom field "cluster" = cluster_name
        └─ Return allocated segment
    ↓
Return VLANAllocationResponse
```

---

## Performance Optimizations

### 1. Thread Pool Architecture

```python
# Separate pools prevent blocking
get_netbox_read_executor()   # 30 workers for fast GETs
get_netbox_write_executor()  # 20 workers for slow POST/PUT/DELETE
```

**Location**: `src/database/netbox_client.py`

### 2. Aggressive Caching Strategy

```python
# Cache durations optimized for NetBox Cloud throttling
_cache = {
    "prefixes": {"ttl": 600},       # 10 minutes (most accessed)
    "vlans": {"ttl": 600},           # 10 minutes
    "redbull_tenant_id": {"ttl": 3600},  # 1 hour (rarely changes)
    "vrfs": {"ttl": 3600},           # 1 hour (static data)
}
```

**Location**: `src/database/netbox_cache.py`

### 3. Request Coalescing

```python
# Prevents duplicate concurrent fetches
if cache_key in _inflight_requests:
    # Wait for in-flight request instead of fetching again
    await _inflight_requests[cache_key]
```

**Location**: `src/database/netbox_cache.py`

### 4. Parallel Data Fetching

```python
# Fetch reference data in parallel using asyncio.gather()
results = await asyncio.gather(
    self._get_vrf(vrf_name),
    self._get_or_create_site(site),
    self._get_tenant("Redbull"),
    self._get_role("Data", "prefix")
)
# Reduces 200ms serial calls to ~50ms (4x faster)
```

**Location**: `src/database/netbox_helpers.py`

### 5. Performance Monitoring

```python
# Built-in timing logs for NetBox operations
if elapsed > 20000:
    logger.error(f"🚨 NETBOX SEVERE THROTTLING: {operation} took {elapsed}ms")
elif elapsed > 5000:
    logger.warning(f"⚠️  NETBOX THROTTLED: {operation} took {elapsed}ms")
```

**Decorator**: `@log_netbox_timing` in `src/database/netbox_utils.py`

---

## Validation Architecture

### Comprehensive Validation (validators.py)

The application implements **defense-in-depth validation** across multiple layers:

#### 1. Input Validation
- **Site**: Must be in configured `SITES` list
- **VLAN ID**: Range 1-4094, warns about reserved VLAN 1
- **EPG Name**: Max 64 chars, alphanumeric + underscore/hyphen only
- **Cluster Name**: Max 100 chars, allows letters/numbers/hyphens/underscores/dots
- **Description**: Max 500 chars, no control characters

#### 2. Network Validation
- **Segment Format**: Must be valid CIDR notation (e.g., `192.168.1.0/24`)
- **Strict Network Address**: Validates network address is correct (not host address)
  - Example: `192.168.1.5/24` → Error, should be `192.168.1.0/24`
- **Site Prefix Enforcement**: IP must start with site's assigned prefix
  - site1 (prefix 192) → Only accepts `192.x.x.x/xx`
- **Subnet Mask Range**: /16 to /29 only
- **No Reserved IPs**: Validates against 0.0.0.0/8, 127.0.0.0/8, etc.
- **Network/Broadcast/Gateway Check**: Ensures segment is a network, not single host

#### 3. Edge Case Validation
- **IP Overlap Detection**: Checks for overlapping subnets
- **EPG Name Uniqueness**: Per-site uniqueness for EPG names with same VLAN ID
- **XSS Injection Prevention**: Sanitizes description and EPG name fields
- **VLAN Conflict Detection**: Prevents duplicate VLAN IDs per site
- **VRF Validation**: Ensures VRF exists in NetBox before creating segment

#### 4. Business Logic Validation
- **Allocation State**: Can't delete allocated segments
- **Release Validation**: Can only release actually allocated segments
- **Cluster Assignment**: Validates cluster name format for shared segments

**Location**: `src/utils/validators.py` (~700+ lines)

---

## Adding New Features

### Recommended Pattern

1. **Models** (`src/models/schemas.py`): Add Pydantic schema
2. **Validators** (`src/utils/validators.py`): Add validation logic
3. **Database** (`src/database/netbox_helpers.py` or `netbox_storage.py`): Add NetBox operations
4. **Service** (`src/services/`): Implement business logic
5. **Routes** (`src/api/routes.py`): Add API endpoint
6. **Frontend** (`static/`): Update UI if needed

### Example: Adding a New Validation Rule

```python
# 1. Add to validators.py
@staticmethod
def validate_custom_field(value: str) -> None:
    if not some_condition:
        raise HTTPException(status_code=400, detail="Error message")

# 2. Use in service
await Validators.validate_custom_field(segment.custom_field)

# 3. Test in test_api.py
def test_custom_field_validation():
    segment = {..., "custom_field": "invalid"}
    response = requests.post(f"{BASE_URL}/segments", json=segment)
    assert response.status_code == 400
```

---

## Common Issues & Troubleshooting

### Issue: Application won't start

**Symptom**: Crash on startup with configuration error

**Solution**: Ensure all sites in `SITES` have entries in `SITE_PREFIXES`

```bash
# Check configuration
export SITES="site1,site2,site3"
export SITE_PREFIXES="site1:192,site2:193,site3:194"
```

### Issue: NetBox connection failed

**Symptom**: `Failed to connect to NetBox` error

**Solution**:
1. Verify `NETBOX_URL` is correct
2. Check `NETBOX_TOKEN` is valid (generate in NetBox: User Menu → API Tokens)
3. Test connectivity: `curl -H "Authorization: Token TOKEN" https://netbox-url/api/status/`

### Issue: Slow performance

**Symptom**: API calls take >5 seconds

**Root Cause**: NetBox Cloud throttling

**Solution**:
- Check logs for throttling warnings
- Cache is already aggressive (10-minute TTL)
- Consider self-hosted NetBox for better performance

### Issue: Tests failing

**Common causes**:
- Server not running at `http://localhost:8000`
- NetBox connection issues
- Invalid test data in environment

**Solution**:
```bash
# Ensure server is running
python main.py

# In another terminal, run tests
pytest tests/test_api.py -v
```

---

## Key Design Patterns

### 1. Service Layer Pattern

```python
# Business logic separated from API routes
class SegmentService:
    @staticmethod
    async def create_segment(segment: Segment):
        # Validation
        await SegmentService._validate_segment_data(segment)
        # Business logic
        segment_data = SegmentService._segment_to_dict(segment)
        # Database operation
        return await DatabaseUtils.create_segment(segment_data)
```

**Location**: `src/services/segment_service.py`

### 2. Repository Pattern (NetBoxStorage)

```python
# Database abstraction layer
class NetBoxStorage:
    async def find(self, query: Dict) -> List[Dict]
    async def insert_one(self, document: Dict) -> Dict
    async def update_one(self, query: Dict, update: Dict) -> bool
    async def delete_one(self, query: Dict) -> bool
```

**Location**: `src/database/netbox_storage.py`

### 3. Data Transfer Objects (Pydantic Models)

```python
# Type-safe request/response models
class Segment(BaseModel):
    site: str
    vlan_id: int = Field(ge=1, le=4094)
    epg_name: str
    segment: str
    vrf: str
    dhcp: bool = False
    # ... with automatic validation
```

**Location**: `src/models/schemas.py`

### 4. Fail-Fast Configuration Validation

```python
# Startup validation prevents runtime errors
async def lifespan(app: FastAPI):
    validate_site_prefixes()  # Crashes if config invalid
    await init_storage()       # Verifies NetBox connection
    yield
    await close_storage()
```

**Location**: `src/app.py`

---

## Important Notes for Claude

1. **This is a production application** - emphasize reliability, validation, error handling
2. **NetBox is the source of truth** - all data operations go through NetBox REST API via pynetbox
3. **Performance is critical** - NetBox Cloud throttles heavily, hence aggressive caching
4. **Fail-fast philosophy** - configuration errors crash at startup, not runtime
5. **Clean architecture** - strict separation between API, services, database, validation
6. **Comprehensive validation** - 700+ lines of validation logic for edge cases
7. **Async throughout** - all I/O operations are async with thread pool executors
8. **Site-specific IP prefixes** - core validation requirement (e.g., site1 = 192.x.x.x)
9. **Modular database layer** - NetBox integration split across 9 focused modules for maintainability
10. **Sequential execution** - Removed unnecessary parallel execution (cache makes it instant anyway)
11. **Site Groups are GET-only** - App does NOT create site groups (read-only tokens supported)

### When Working on This Codebase

- **Always validate input** - add to `validators.py`, use in services
- **Invalidate cache on writes** - call `invalidate_cache()` after NetBox modifications
- **Log timing for NetBox calls** - use `@log_netbox_timing` decorator from `netbox_client.py`
- **Test edge cases** - see `test_comprehensive.py` for examples
- **Follow service pattern** - API → Service → NetBoxCRUDOps/NetBoxQueryOps → NetBox
- **Use the right module** - When adding NetBox functionality:
  - **Client/executors**: `netbox_client.py` - NetBox client, thread pools, timing decorators
  - **Cache management**: `netbox_cache.py` - TTL-based caching, request coalescing
  - **Object helpers**: `netbox_helpers.py` - Get/create VRF, VLAN, Tenant, Role, Site, VLAN Group
  - **CRUD operations**: `netbox_crud_ops.py` - Create, update, delete segments
  - **Query operations**: `netbox_query_ops.py` - Find, count, optimized queries
  - **Utilities**: `netbox_utils.py` - Safe attribute access, data conversion (prefix_to_segment)
  - **Constants**: `netbox_constants.py` - Centralized constants (no magic strings)
  - **Main interface**: `netbox_storage.py` - Public API, initialization, pre-fetching

---

## Dependencies

**Python**: 3.11+

**Key Packages** (from requirements.txt):
- `fastapi==0.104.1` - Web framework
- `uvicorn[standard]==0.24.0` - ASGI server
- `pydantic==2.5.0` - Data validation
- `pynetbox==7.3.3` - NetBox API client
- `pandas==2.1.4` - Data export
- `openpyxl==3.1.2` - Excel export
- `requests==2.31.0` - HTTP client
- `python-multipart==0.0.6` - File uploads

**Test Framework**: pytest (not in requirements.txt, install separately for testing)

---

**Version**: v3.2.0 (Database Layer Simplification & Production Fixes)
**Last Updated**: 2025-12-06
**Maintainer**: VLAN Manager Team

---

## Recent Improvements (v3.2.0 - December 2025)

### Database Layer Simplifications

**1. Removed Unnecessary Parallelization** (Commit: f099070)
- **Problem**: Over-optimization after fixing 1000 API calls bug
- **Solution**: Removed `asyncio.gather()` for cached lookups (VRF, Site, Tenant, Role)
- **Result**: Removed ~40 lines of complexity, same performance (cache hits are <1ms anyway)
- **Kept**: One useful parallel execution in `_update_vlan_if_changed()` (2 real API calls)

**2. Fixed Site Group Creation** (Commit: 7a37984) - **CRITICAL**
- **Problem**: Code was creating site groups without permissions (production tokens are read-only)
- **Solution**: Changed `get_or_create_site()` → `get_site()` (GET only, no CREATE)
- **Result**: Works with read-only tokens, clear error if site group missing
- **Impact**: Production-ready, no DCIM write permissions needed

**3. Modular Refactoring** (Commit: b15bb41)
- **Before**: Monolithic files, parallel execution everywhere
- **After**: 9 focused modules, sequential where cache makes it instant
- **Result**: Removed ~100-150 lines of boilerplate, cleaner architecture

**Total Impact**:
- ✅ Removed ~180-220 lines of unnecessary complexity
- ✅ Fixed critical production permission issue
- ✅ Same performance (cache makes parallelization unnecessary)
- ✅ Much more readable and maintainable

### Cache Optimizations

**TTL Tuning** (matches actual usage patterns):
```python
# Static data (rarely changes) - 1 hour
VRF, Tenant, Role, Site Groups: 3600s TTL → ~99% hit rate

# Dynamic data (changes frequently) - 10 minutes
Prefixes, VLANs: 600s TTL → ~75-80% hit rate
```

**Performance**:
- Cache hit: <1ms (in-memory dict lookup)
- Cache miss: ~50-200ms (NetBox API call)
- **Result**: 100-200x speedup for cached data

### Architecture Improvements

**Separation of Concerns**:
- `netbox_crud_ops.py` - Create/Update/Delete (344 lines)
- `netbox_query_ops.py` - Read/Query (198 lines)
- `netbox_helpers.py` - Object helpers (360 lines)
- `netbox_constants.py` - No magic strings (57 lines)

**KISS Principle Applied**:
- Removed parallel execution for cached lookups
- Simple sequential code (easier to debug)
- Only parallelize when actually beneficial (uncached API calls)

---
