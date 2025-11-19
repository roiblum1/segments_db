# CLAUDE.md - VLAN Manager Architecture Guide

> Generated on 2025-11-17 for Claude AI assistants
> This document provides architectural context for understanding and working with the VLAN Manager codebase

## Project Overview

**VLAN Manager** is a production-grade network VLAN allocation and management system that provides an intelligent API layer on top of NetBox IPAM. It automates VLAN segment allocation for clusters across multiple sites with VRF support, comprehensive validation, and a modern web interface.

**Type**: FastAPI Web Application + REST API  
**Primary Language**: Python 3.11  
**Architecture Pattern**: Clean Architecture with service-oriented design  
**Storage Backend**: NetBox (IPAM system with PostgreSQL backend)  
**Deployment**: Containerized (Docker/Podman), Kubernetes/OpenShift ready

---

## 🏗️ Architecture Overview

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                      VLAN Manager                           │
│  (Intelligent API Layer + Business Logic + Validation)     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    NetBox IPAM                              │
│  (Persistent Storage + REST API + PostgreSQL Backend)      │
└─────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **NetBox as Backend**: Uses NetBox's professional IPAM system instead of local database
   - Provides PostgreSQL scalability
   - Professional UI for network administrators
   - Audit trails and change logging
   - Multi-user support with permissions

2. **Clean Architecture**: Separation of concerns with distinct layers
   - API Layer (routes.py)
   - Service Layer (allocation, segment, stats, export, logs services)
   - Database Layer (netbox_storage.py)
   - Models (Pydantic schemas)
   - Utilities (validators, database_utils)

3. **Async/Await Pattern**: Fully asynchronous for performance
   - Thread pool executors for NetBox I/O operations
   - Separate pools for read (30 workers) vs write (20 workers) operations
   - Request coalescing to prevent duplicate API calls

4. **Aggressive Caching**: 10-minute cache for NetBox queries
   - Reduces API calls to NetBox Cloud (which throttles heavily)
   - In-flight request tracking prevents concurrent duplicate fetches
   - Cache invalidation on write operations

---

## 📁 Directory Structure

```
segments_2/
├── main.py                 # Entry point (delegates to src/run.py)
├── requirements.txt        # Python dependencies
├── Dockerfile             # Container image definition
├── .env.example           # Environment configuration template
├── README.md              # User documentation
│
├── src/                   # Application source code
│   ├── run.py            # Server startup (uvicorn)
│   ├── app.py            # FastAPI application setup, lifespan, middleware
│   │
│   ├── api/              # REST API endpoints
│   │   └── routes.py     # All API routes (~130 lines)
│   │
│   ├── config/           # Configuration and settings
│   │   └── settings.py   # Environment variables, validation, logging
│   │
│   ├── database/         # NetBox storage integration
│   │   └── netbox_storage.py  # NetBox API wrapper (~1345 lines)
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
│   └── test_api.py      # Integration tests
│
├── deploy/               # Deployment configurations
│   ├── helm/            # Kubernetes Helm chart
│   └── scripts/         # Podman deployment scripts
│
└── logs/                 # Application logs (runtime)
```

**Total Source Code**: ~3,980 lines of Python

---

## 🔄 Data Flow & Architecture Patterns

### 1. Application Startup Flow

```python
# main.py → src/run.py → src/app.py

# Startup sequence (in app.py lifespan):
1. Validate site prefixes configuration (CRITICAL - fails fast)
2. Initialize NetBox client connection
3. Verify NetBox API connectivity
4. Sync existing VLANs from NetBox (tenant: Redbull)
5. Start FastAPI server
```

### 2. Request Flow (Example: Allocate VLAN)

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

### 3. NetBox Data Mapping

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

---

## 🔌 API Endpoints

### Core Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/allocate-vlan` | Allocate VLAN segment to cluster |
| `POST` | `/api/release-vlan` | Release VLAN allocation |
| `GET` | `/api/segments` | List segments (filters: site, allocated) |
| `GET` | `/api/segments/search` | Search segments by query |
| `POST` | `/api/segments` | Create new segment |
| `GET` | `/api/segments/{id}` | Get specific segment |
| `PUT` | `/api/segments/{id}` | Update segment |
| `DELETE` | `/api/segments/{id}` | Delete segment |
| `POST` | `/api/segments/bulk` | Bulk create segments (CSV) |
| `GET` | `/api/sites` | Get configured sites |
| `GET` | `/api/vrfs` | Get available VRFs from NetBox |
| `GET` | `/api/stats` | Site statistics |
| `GET` | `/api/health` | Health check with system status |
| `GET` | `/api/export/segments/csv` | Export segments to CSV |
| `GET` | `/api/export/segments/excel` | Export segments to Excel |
| `GET` | `/api/logs` | View application logs |

**Interactive API Docs**: Available at `/docs` (Swagger UI)

---

## 🔐 Configuration & Environment Variables

### Required Configuration

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

### Optional Configuration

```bash
# NetBox SSL
NETBOX_SSL_VERIFY="true"  # Set false for self-signed certs

# Server
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"

# Logging
LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR
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

## 🛡️ Validation Architecture

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

---

## 🚀 Performance Optimizations

### 1. Thread Pool Architecture

```python
# Separate pools prevent blocking
get_netbox_read_executor()   # 30 workers for fast GETs
get_netbox_write_executor()  # 20 workers for slow POST/PUT/DELETE
```

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

### 3. Request Coalescing

```python
# Prevents duplicate concurrent fetches
if cache_key in _inflight_requests:
    # Wait for in-flight request instead of fetching again
    await _inflight_requests[cache_key]
```

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

### 5. Performance Monitoring

```python
# Built-in timing logs for NetBox operations
if elapsed > 20000:
    logger.error(f"🚨 NETBOX SEVERE THROTTLING: {operation} took {elapsed}ms")
elif elapsed > 5000:
    logger.warning(f"⚠️  NETBOX THROTTLED: {operation} took {elapsed}ms")
```

---

## 🔍 Key Design Patterns

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

### 2. Repository Pattern (NetBoxStorage)

```python
# Database abstraction layer
class NetBoxStorage:
    async def find(self, query: Dict) -> List[Dict]
    async def insert_one(self, document: Dict) -> Dict
    async def update_one(self, query: Dict, update: Dict) -> bool
    async def delete_one(self, query: Dict) -> bool
```

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

### 4. Fail-Fast Configuration Validation

```python
# Startup validation prevents runtime errors
async def lifespan(app: FastAPI):
    validate_site_prefixes()  # Crashes if config invalid
    await init_storage()       # Verifies NetBox connection
    yield
    await close_storage()
```

---

## 🗄️ Data Models

### Core Pydantic Schemas (models/schemas.py)

```python
class Segment(BaseModel):
    site: str                          # Site identifier
    vlan_id: int                       # VLAN ID (1-4094)
    epg_name: str                      # Endpoint group name
    segment: str                       # IP network (CIDR)
    vrf: str                          # VRF/Network name
    dhcp: bool = False                # DHCP enabled
    description: Optional[str] = ""   # User notes
    cluster_name: Optional[str] = None  # Allocated cluster
    allocated_at: Optional[datetime] = None
    released: bool = False
    released_at: Optional[datetime] = None

class VLANAllocationRequest(BaseModel):
    cluster_name: str
    site: str
    vrf: str  # Required for allocation

class VLANAllocationResponse(BaseModel):
    vlan_id: int
    cluster_name: str
    site: str
    segment: str
    epg_name: str
    vrf: str
    allocated_at: datetime
```

### NetBox Object Relationships

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

## 🔧 Development Workflow

### Local Development Setup

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with NetBox credentials and site configuration

# 4. Run application
python main.py
# Server starts on http://localhost:8000
```

### Testing

```bash
# Run integration tests (requires running server)
pytest tests/test_api.py -v

# Comprehensive test suite (80+ edge case tests)
python test_comprehensive.py
```

### Adding New Features

**Follow this pattern**:

1. **Models** (`src/models/schemas.py`): Add Pydantic schema
2. **Validators** (`src/utils/validators.py`): Add validation logic
3. **Database** (`src/database/netbox_storage.py`): Add NetBox operations
4. **Service** (`src/services/`): Implement business logic
5. **Routes** (`src/api/routes.py`): Add API endpoint
6. **Frontend** (`static/`): Update UI if needed

**Example: Adding a new validation rule**

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

## 🐳 Deployment

### Container Deployment

```bash
# Build
docker build -t vlan-manager .

# Run
docker run -d \
  --name vlan-manager \
  -p 8000:8000 \
  -e NETBOX_URL="https://netbox.example.com" \
  -e NETBOX_TOKEN="token" \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  vlan-manager
```

### Kubernetes/OpenShift

```bash
# Using Helm chart
helm install vlan-manager ./deploy/helm \
  --set config.netboxUrl="https://netbox.example.com" \
  --set config.netboxToken="token" \
  --set config.sites="site1,site2,site3" \
  --set config.sitePrefixes="site1:192,site2:193,site3:194"
```

### Health Monitoring

```bash
# Health check endpoint
curl http://localhost:8000/api/health

# Response includes:
# - NetBox connectivity status
# - Per-site segment statistics
# - Storage operation validation
# - System-wide metrics
```

---

## 🔐 Security Considerations

### Authentication & Authorization
- **NetBox API Token**: Stored in environment variable, not in code
- **No Built-in Auth**: Relies on NetBox's permission system
- **Network Security**: Deploy behind reverse proxy with TLS

### Input Sanitization
- **XSS Prevention**: Validates and sanitizes description and EPG name fields
- **SQL Injection**: Not applicable (uses NetBox REST API, not direct SQL)
- **Path Traversal**: Not applicable (no file uploads)

### API Rate Limiting
- **NetBox Cloud Throttling**: Automatically detected and logged
- **Retry Logic**: Exponential backoff for throttled requests (error_handlers.py)

---

## 📊 Logging & Monitoring

### Log Configuration

```python
# Rotating file handler: 50MB per file, keep 5 backups (250MB total)
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Log Locations
- **Application Logs**: `vlan_manager.log` (rotating)
- **Web UI Access**: `GET /api/logs?lines=100`

### Key Log Messages

```python
# Performance warnings
"⚠️  NETBOX THROTTLED: operation took Xms"
"🚨 NETBOX SEVERE THROTTLING: operation took Xms"

# Business logic
"Allocated VLAN {vlan_id} (EPG: {epg_name}, VRF: {vrf}) to {cluster}"
"Released VLAN for {cluster} at {site}"

# Validation errors
"Invalid site requested: {site}, valid sites: {SITES}"
"IP prefix mismatch for site '{site}': expected '{prefix}'"
```

---

## 🚨 Common Issues & Troubleshooting

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

### Issue: Allocation fails with "No available segments"

**Symptom**: 503 error when allocating VLAN

**Solution**:
1. Check if segments exist for that site+VRF: `GET /api/segments?site=site1`
2. Verify segments are not all allocated
3. Create new segments via UI or API

---

## 📚 Additional Resources

### Project Documentation
- **README.md**: User-facing documentation, deployment guides
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Help Page**: http://localhost:8000/static/html/help.html

### NetBox Integration
- **NetBox API Docs**: https://netbox.readthedocs.io/en/stable/rest-api/overview/
- **pynetbox Library**: https://github.com/netbox-community/pynetbox

### Related Files
- **.env.example**: Environment variable template
- **requirements.txt**: Python dependencies
- **Dockerfile**: Container image definition
- **deploy/helm/values.yaml**: Kubernetes configuration

---

## 🎯 Key Takeaways for Claude

1. **This is a production application** - emphasize reliability, validation, error handling
2. **NetBox is the source of truth** - all data operations go through NetBox REST API
3. **Performance is critical** - NetBox Cloud throttles heavily, hence aggressive caching
4. **Fail-fast philosophy** - configuration errors crash at startup, not runtime
5. **Clean architecture** - strict separation between API, services, database, validation
6. **Comprehensive validation** - 700+ lines of validation logic for edge cases
7. **Async throughout** - all I/O operations are async with thread pool executors
8. **Site-specific IP prefixes** - core validation requirement (e.g., site1 = 192.x.x.x)

### When Working on This Codebase

- **Always validate input** - add to validators.py, use in services
- **Invalidate cache on writes** - call `invalidate_cache()` after NetBox modifications
- **Log timing for NetBox calls** - use `@log_netbox_timing` decorator
- **Test edge cases** - see test_comprehensive.py for examples
- **Follow service pattern** - API → Service → DatabaseUtils → NetBoxStorage → NetBox

---

**Version**: v3.1.0 (NetBox Integration with Edge Case Validation)  
**Last Updated**: 2025-11-17  
**Maintainer**: VLAN Manager Team
