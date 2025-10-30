# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Local development (ensure virtual environment is activated)
python main.py

# Or directly via uvicorn
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload

# Container deployment
podman build -t vlan-manager .
podman run -d --name vlan-manager -p 8000:8000 \
  -v ./data:/app/data \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  vlan-manager
```

### Testing and Validation
```bash
# View application logs (last 100 lines)
tail -n 100 vlan_manager.log

# Health check
curl http://localhost:8000/api/health

# Check data file
cat data/segments.json
```

### Container Management
```bash
# View logs
podman logs vlan-manager

# Check health status
podman healthcheck run vlan-manager

# Restart container
podman restart vlan-manager
```

## Architecture Overview

### Core Design Pattern
This is a **FastAPI-based RESTful API** with **JSON file storage** backend following a clean layered architecture:

```
┌─────────────────────────────────────────┐
│  API Layer (routes.py)                  │ ← FastAPI endpoints
├─────────────────────────────────────────┤
│  Service Layer (services/)              │ ← Business logic
│  - AllocationService                    │
│  - SegmentService                       │
│  - StatsService, ExportService, etc.    │
├─────────────────────────────────────────┤
│  Utils Layer (utils/)                   │ ← Database ops & validation
│  - DatabaseUtils                        │
│  - Validators                           │
├─────────────────────────────────────────┤
│  Models (schemas.py)                    │ ← Pydantic models
├─────────────────────────────────────────┤
│  Storage (json_storage.py)              │ ← JSON file storage with locking
└─────────────────────────────────────────┘
```

### Critical Architecture Concepts

**1. Startup Validation (Fail-Fast Pattern)**
- Application validates ALL configuration during startup via `validate_site_prefixes()`
- Located in [src/app.py](src/app.py:19-22) `lifespan` function
- **MUST crash immediately** if any site lacks an IP prefix
- This prevents runtime errors by catching configuration issues early

**2. Atomic VLAN Allocation with File Locking**
- Uses `filelock` library for thread-safe file operations
- Prevents race conditions when multiple requests access the JSON file simultaneously
- Atomic read-modify-write operations in [src/database/json_storage.py](src/database/json_storage.py)
- Implemented in [src/utils/database_utils.py](src/utils/database_utils.py) `find_and_allocate_segment()`

**3. Site IP Prefix Validation**
- Each site has a specific IP prefix (e.g., site1 = 192.x.x.x)
- Configured via `SITE_PREFIXES` environment variable
- Validation enforced at segment creation via [src/utils/validators.py](src/utils/validators.py)
- Ensures segments match their site's IP range

**4. JSON File Storage**
- All data stored in `segments.json` file in DATA_DIR
- File structure: `{"segments": [...], "next_id": 1}`
- Atomic writes using temporary file and rename
- File locking prevents concurrent modification issues

### Key Services

**AllocationService** ([src/services/allocation_service.py](src/services/allocation_service.py))
- `allocate_vlan()`: Find available segment and atomically assign to cluster
- `release_vlan()`: Mark segment as released for reuse

**SegmentService** ([src/services/segment_service.py](src/services/segment_service.py))
- CRUD operations for segments
- Search and filtering (by site, allocation status)
- Bulk import from CSV

**Validators** ([src/utils/validators.py](src/utils/validators.py))
- `validate_site()`: Ensure site exists in configuration
- `validate_segment_format()`: Verify IP prefix matches site AND network format is correct
- `validate_epg_name()`: Prevent empty/whitespace EPG names

### Data Flow Example: VLAN Allocation

```
Client POST /api/allocate-vlan
  ↓
[routes.py] allocate_vlan() endpoint
  ↓
[AllocationService] validate site → check existing allocation
  ↓
[DatabaseUtils] find_and_allocate_segment() - atomic file operation with locking
  ↓
[JSONStorage] read JSON → find available → update → write atomically
  ↓
Updates: cluster_name, allocated_at, released=false
  ↓
Returns: VLANAllocationResponse
```

## Environment Configuration

### Required Variables
```bash
SITES="site1,site2,site3"  # Comma-separated list
SITE_PREFIXES="site1:192,site2:193,site3:194"  # CRITICAL: Must match SITES
```

### Optional Variables
```bash
DATA_DIR="/app/data"  # Directory for JSON data storage (default: /app/data)
LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"
```

### Configuration Validation Rules
1. **All sites MUST have IP prefixes** - application crashes on startup if missing
2. Sites list and prefixes must be synchronized
3. Data directory must be writable for JSON storage
4. In containerized environments, mount a volume to DATA_DIR for persistence

## Data Storage

### JSON File Structure
```json
{
  "segments": [
    {
      "_id": "1",
      "site": "site1",
      "vlan_id": 100,
      "epg_name": "EPG_PROD_01",
      "segment": "192.168.1.0/24",
      "description": "Production segment",
      "cluster_name": "cluster-prod-01",
      "allocated_at": "2024-01-15T10:30:00Z",
      "released": false,
      "released_at": null
    }
  ],
  "next_id": 2
}
```

### File Locking Mechanism
- Uses `FileLock` from `filelock` library
- Lock file: `segments.json.lock`
- Timeout: 10 seconds
- All database operations execute within lock context

### Persistence Strategies

**Local Development:**
- Data stored in local directory (default: `/app/data`)
- Survives application restarts but not container recreation

**Container with Volume:**
```bash
podman run -v ./data:/app/data vlan-manager
```

**OpenShift/Kubernetes with PVC:**
- PVC mounted at `/app/data`
- Data persists across pod restarts and redeployments
- See [deploy/helm/values.yaml](deploy/helm/values.yaml) for configuration

## Common Development Patterns

### Adding a New API Endpoint
1. Define Pydantic model in [src/models/schemas.py](src/models/schemas.py)
2. Add service method in appropriate service class (e.g., `SegmentService`)
3. Add storage operation in [src/database/json_storage.py](src/database/json_storage.py) if needed
4. Create route in [src/api/routes.py](src/api/routes.py)
5. Add validation in [src/utils/validators.py](src/utils/validators.py) if needed

### Adding a New Validator
- All validators are static methods in `Validators` class
- Raise `HTTPException` with appropriate status code and detail message
- Include DEBUG-level logging for troubleshooting

### Modifying Configuration
- Configuration is loaded ONCE at startup from environment variables
- Changes require application restart
- All config is in [src/config/settings.py](src/config/settings.py)

## Logging Configuration

**Log Level Control**: Set via `LOG_LEVEL` environment variable
- Defaults to `INFO`
- Supports: DEBUG, INFO, WARNING, ERROR, CRITICAL

**Log Output**:
- stdout (container logs)
- `vlan_manager.log` file in application root

**Log Format**:
```
%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] %(funcName)s() - %(message)s
```

## Deployment Modes

### 1. Local Development
```bash
export SITES="site1,site2,site3"
export SITE_PREFIXES="site1:192,site2:193,site3:194"
export DATA_DIR="./data"
python main.py
```

### 2. Container (Podman/Docker)
- Dockerfile: [Dockerfile](Dockerfile)
- **Volume mount required**: `-v ./data:/app/data`
- Health check: `curl -f http://localhost:8000/api/health`
- Health check interval: 30s, timeout: 10s, start period: 60s

### 3. Air-Gapped Deployment
- Build: `./deploy/scripts/build-and-save.sh`
- Transfer: `deploy/podman/vlan-manager-*.tar` AND the data directory
- Deploy: `./deploy/scripts/load-and-run.sh`

### 4. Kubernetes/OpenShift (Helm)
- Chart location: [deploy/helm/](deploy/helm/)
- Install: `helm install vlan-manager ./deploy/helm`
- **PVC automatically created** for persistent storage
- Data mounted at `/app/data` from PVC

## Critical Behaviors to Preserve

1. **Atomicity**: VLAN allocation MUST use file locking to prevent race conditions
2. **Validation**: Site prefix validation is mandatory and enforced at multiple layers
3. **Fail-Fast**: Configuration errors must crash the application at startup, not during runtime
4. **Idempotency**: Allocating VLAN for same cluster+site returns existing allocation
5. **Strict Network Format**: IP segments must be in proper CIDR network format (e.g., 192.168.0.0/24, not 192.168.0.1/24)
6. **File Locking**: All JSON file operations MUST acquire lock before read/write

## Frontend Assets

- Static files: [static/](static/) directory
- HTML: [static/html/index.html](static/html/index.html)
- CSS: [static/css/](static/css/) - includes dark mode support
- JavaScript: [static/js/](static/js/)
- Caching: Static assets cached for 1 year, HTML for 1 hour

## API Documentation

Interactive API docs available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Backup and Migration

### Backing Up Data
```bash
# Container
podman cp vlan-manager:/app/data/segments.json ./backup-segments.json

# Kubernetes
kubectl cp <pod-name>:/app/data/segments.json ./backup-segments.json
```

### Restoring Data
```bash
# Container
podman cp ./backup-segments.json vlan-manager:/app/data/segments.json
podman restart vlan-manager

# Kubernetes
kubectl cp ./backup-segments.json <pod-name>:/app/data/segments.json
kubectl delete pod <pod-name>  # Will be recreated
```

## Troubleshooting

### Data File Issues
- **File not found**: Container creates empty file on first run
- **Permission denied**: Ensure DATA_DIR is writable (chmod 777 in Dockerfile)
- **Corrupted JSON**: Application reinitializes empty file on corruption detection
- **Lock timeout**: Check for hung processes or adjust timeout in json_storage.py

### Common Errors
```bash
# Check data file exists
ls -la /app/data/segments.json

# Check file permissions
ls -ld /app/data

# View current data
cat /app/data/segments.json | jq .
```
