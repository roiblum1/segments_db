# Coding Conventions

**Analysis Date:** 2026-03-27

## Naming Patterns

**Files:**
- Python modules: `lowercase_with_underscores.py`
- Package directories: `lowercase` (e.g., `src/services/`, `src/utils/validators/`)
- Test files: `test_*.py` (e.g., `test_api.py`, `test_comprehensive.py`)
- API routes: `routes.py`
- Service classes: `*_service.py` (e.g., `segment_service.py`, `allocation_service.py`)
- Database modules: `netbox_*.py` (e.g., `netbox_storage.py`, `netbox_helpers.py`, `netbox_cache.py`)
- Validator modules: `*_validators.py` (e.g., `input_validators.py`, `network_validators.py`)

**Classes:**
- PascalCase for all classes: `NetBoxHelpers`, `SegmentService`, `InputValidators`, `Validators`
- Service classes end with `Service`: `AllocationService`, `SegmentService`, `StatsService`
- Validator classes end with `Validators`: `InputValidators`, `NetworkValidators`, `SecurityValidators`
- Helper classes use `Helpers`: `NetBoxHelpers`
- Exception classes use descriptive names: `NetBoxAPIError`, `NetworkTimeoutError`, `ConcurrentModificationError`

**Functions:**
- snake_case for all functions: `validate_site()`, `get_cached()`, `find_and_allocate_segment()`
- Static methods in service/validator classes: `@staticmethod async def allocate_vlan(...)`
- Async functions always async/await: `async def create_segment(...)`
- Private functions/methods start with underscore: `_validate_segment_data()`, `_cleanup_test_segments()`

**Variables:**
- snake_case for all variables: `segment_data`, `site_slug`, `cluster_name`, `vlan_id`
- Constants: UPPERCASE_WITH_UNDERSCORES (e.g., `TENANT_REDBULL`, `CACHE_TTL_LONG`, `STATUS_ACTIVE`)
- Configuration variables: UPPERCASE_WITH_UNDERSCORES (e.g., `NETBOX_URL`, `NETBOX_TOKEN`, `SITES`)
- Cache entries and internal state: lowercase with underscores (e.g., `_cache`, `_inflight_requests`, `_netbox_client`)

**Types:**
- Pydantic models: PascalCase, inherit from `BaseModel` (e.g., `Segment`, `VLANAllocationRequest`, `VLANAllocationResponse`)
- Type hints used throughout: `Dict[str, Any]`, `List[Dict[str, Any]]`, `Optional[str]`
- Generic types: `from typing import Optional, List, Dict, Any, Callable`

## Code Style

**Formatting:**
- No explicit formatter configured (no black, prettier config detected)
- Implicit standard: 4-space indentation (Python standard)
- Line length: Varies (no enforced limit found), but generally readable
- Docstring style: Google-style docstrings with parameter descriptions and return types

**Linting:**
- No explicit linter config (no .eslintrc, .pylintrc detected)
- Code relies on implicit conventions and pytest validation

**Spacing and Structure:**
- Two blank lines between top-level class/function definitions
- One blank line between methods in classes
- Imports organized by: stdlib, third-party, local (implicit)
- All imports at top of file

Example from `src/api/routes.py`:
```python
from typing import Optional, List
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Response, Request
from starlette.responses import JSONResponse

from ..models.schemas import (
    VLANAllocationRequest, VLANAllocationResponse,
    VLANRelease, Segment, LoginRequest, LoginResponse, AuthStatusResponse
)
from ..services.allocation_service import AllocationService
from ..services.segment_service import SegmentService
```

## Import Organization

**Order:**
1. Standard library imports (logging, sys, os, asyncio, etc.)
2. Third-party library imports (fastapi, pydantic, pynetbox, etc.)
3. Relative local imports (from ..models, from ..services, etc.)

**Path Aliases:**
- No configured path aliases found
- Uses explicit relative imports: `from ..models.schemas import Segment`
- Consistent use of relative paths from module location

**Common Import Patterns:**

From `src/services/segment_service.py`:
```python
import logging
from typing import Optional, List, Dict, Any

from ..models.schemas import Segment
from ..utils.database_utils import DatabaseUtils
from ..utils.validators import Validators
from ..utils.error_handlers import handle_netbox_errors, retry_on_network_error
from ..utils.logging_decorators import log_operation_timing
```

## Error Handling

**Patterns:**
- HTTPException from FastAPI for API errors: `raise HTTPException(status_code=400, detail="Error message")`
- Custom exceptions for domain-specific errors:
  - `NetBoxAPIError(message, status_code, original_error)`
  - `NetworkTimeoutError("Operation failed...")`
  - `ConcurrentModificationError(...)`
- Try-except blocks with specific exception types, not bare except
- Log errors with `logger.error()`, `logger.warning()` with context
- Never suppress exceptions silently

Example from `src/utils/error_handlers.py`:
```python
try:
    return await func(*args, **kwargs)
except (requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.RequestException,
        NetworkTimeoutError) as e:
    last_exception = e
    # ... retry logic
except HTTPException:
    # Don't retry on HTTPExceptions (validation errors, etc.)
    raise
except Exception as e:
    logger.error(f"Non-retryable error in {func.__name__}: {e}")
    raise
```

**Validation Error Pattern:**
- Always use `HTTPException(status_code=400/422/503, detail="Clear message")`
- Include examples or expected format in error messages
- Log validation failures with `logger.warning()` before raising

## Logging

**Framework:** Python's standard `logging` module

**Setup:**
- Logger created per module: `logger = logging.getLogger(__name__)`
- Centralized logging configuration: `src/config/settings.py` has `setup_logging()` function
- Log levels used throughout: DEBUG, INFO, WARNING, ERROR

**Patterns:**

Entry/exit logging in services:
```python
logger.info(f"Allocation request: cluster={request.cluster_name}, site={request.site}, vrf={request.vrf}")
```

Debug logging for detailed operations:
```python
logger.debug(f"Validating site: {site}")
logger.debug(f"Cache HIT for {key} (age: {age:.1f}s)")
```

Warning for validation failures:
```python
logger.warning(f"Invalid site: {site}, valid sites: {SITES}")
```

Error logging with context:
```python
logger.error(f"Failed to connect to NetBox: {e}", exc_info=True)
```

**When to Log:**
- DEBUG: Entry/exit from functions, cache hits/misses, parameter values
- INFO: Important operations starting (allocation, creation, deletion), configuration loaded
- WARNING: Validation failures, recoverable issues, performance warnings
- ERROR: Unrecoverable failures, exceptions with context

## Comments

**When to Comment:**
- Complex business logic (e.g., VRF/network/site combinations)
- Non-obvious validation rules (e.g., why certain IP ranges are reserved)
- Performance decisions (e.g., why caching is aggressive)
- Integration points with external systems (NetBox API behavior)

**JSDoc/TSDoc:**
- Python docstrings used, not JSDoc
- Google-style docstrings for functions and classes:

Example from `src/database/netbox_helpers.py`:
```python
async def get_site(self, site_slug: str):
    """Get site group from NetBox (must already exist - no creation)

    Tries exact match first, then falls back to lowercase for compatibility.
    This handles both uppercase slugs (production) and lowercase slugs (test).
    """
```

Example from `src/services/allocation_service.py`:
```python
@staticmethod
async def release_vlan(cluster_name: str, site: str, vrf: str) -> Dict[str, str]:
    """Release a VLAN segment allocation

    Args:
        cluster_name: Name of the cluster to release
        site: Site name
        vrf: VRF/Network name (required to ensure correct network matching)
    """
```

## Function Design

**Size:**
- Most functions 10-50 lines
- Service layer functions tend toward shorter (5-15 lines) with delegation to utilities
- Validation functions are typically 10-30 lines with detailed validation steps

**Parameters:**
- Prefer explicit parameters over **kwargs
- Use type hints for all parameters: `segment: Segment`, `site: str`
- Optional parameters with `Optional[str] = None`
- No default mutable objects as parameters

**Return Values:**
- Always specify return type: `-> Dict[str, Any]`, `-> List[Dict[str, Any]]`, `-> bool`
- Async functions return actual values, not coroutines (async/await handles that)
- Consistent return types across similar functions

Example pattern:
```python
@staticmethod
async def create_segment(segment: Segment) -> Dict[str, str]:
    """Create a new segment"""
    # Validation
    await SegmentService._validate_segment_data(segment)
    # Conversion
    segment_data = SegmentService._segment_to_dict(segment)
    # Database operation
    result = await DatabaseUtils.create_segment(segment_data)
    # Return
    return {"message": "Segment created", "id": result.get("_id")}
```

## Module Design

**Exports:**
- Each module has clear responsibilities (single responsibility principle)
- Service modules export Service class with static methods
- Validator modules export unified `Validators` class aggregating specialized validators
- Database modules export storage classes and helper functions

**Example - Unified Validators Class:**

`src/utils/validators/__init__.py` aggregates all specialized validators:
```python
class Validators:
    """Unified validators class - aggregates all validation methods for backward compatibility"""

    # Input validation methods
    validate_site = staticmethod(InputValidators.validate_site)
    validate_epg_name = staticmethod(InputValidators.validate_epg_name)
    # ... and so on

    # Network validation methods
    validate_segment_format = staticmethod(NetworkValidators.validate_segment_format)
    # ... and so on
```

This allows code to use `Validators.validate_site()` without worrying about which module it's from.

**Barrel Files:**
- `src/utils/validators/__init__.py`: Re-exports all validator classes and unified Validators class
- `src/database/__init__.py`: Exports public API functions (init_storage, close_storage, get_storage)
- Explicit `__all__` exports in modules with public APIs

Example from `src/database/__init__.py`:
```python
__all__ = [
    "NetBoxStorage",
    "init_storage",
    "close_storage",
    "get_storage"
]
```

## Constants and Configuration

**Location:**
- Magic strings eliminated using `src/database/netbox_constants.py`
- Configuration from environment variables in `src/config/settings.py`
- No hardcoded values in business logic

**Pattern:**
```python
# In netbox_constants.py
TENANT_REDBULL = "RedBull"
ROLE_DATA = "Data"
STATUS_ACTIVE = "active"
CACHE_TTL_LONG = 3600  # 1 hour
```

**Usage:**
```python
from .netbox_constants import TENANT_REDBULL, CACHE_TTL_LONG

tenant = await get_tenant(TENANT_REDBULL)
set_cache(key, data, ttl=CACHE_TTL_LONG)
```

## Decorators

**Common Decorators Used:**

1. **Error Handling:**
   ```python
   @handle_netbox_errors
   async def allocate_vlan(request):
       ...
   ```

2. **Retry Logic:**
   ```python
   @retry_on_network_error(max_retries=3, delay=1.0, backoff=2.0)
   async def find_and_allocate_segment():
       ...
   ```

3. **Operation Timing:**
   ```python
   @log_operation_timing("allocate_vlan", threshold_ms=2000)
   async def allocate_vlan(request):
       ...
   ```

4. **Authentication:**
   ```python
   async def create_segment(
       segment: Segment,
       _: bool = Depends(require_auth)
   ):
       ...
   ```

Decorators are stacked in this order (top to bottom):
1. `@staticmethod` (if applicable)
2. `@handle_netbox_errors` (error handling)
3. `@retry_on_network_error` (retry logic)
4. `@log_operation_timing` (performance monitoring)

## Async/Await Patterns

**All I/O operations are async:**
- Database queries: `await DatabaseUtils.get_segments(...)`
- NetBox API calls: `await run_netbox_get(...)`
- Service layer: All methods are `async def`
- API routes: All handlers are `async def`

**Thread Pool Execution:**
- NetBox API calls run in thread pools to avoid blocking
- Read operations: 30 worker threads (`get_netbox_read_executor()`)
- Write operations: 20 worker threads (`get_netbox_write_executor()`)

**No Parallel Execution for Cached Operations:**
- Sequential execution when all data is cached (instant anyway)
- Parallel execution only when real API calls are needed

Example from `src/database/netbox_helpers.py`:
```python
# Sequential (all cached, instant)
vrf = await self._get_vrf(vrf_name)
site = await self._get_or_create_site(site)
tenant = await self._get_tenant("Redbull")
role = await self._get_role("Data", "prefix")

# Could be parallel, but sequential is faster when cached
```

## Test-Driven Patterns

**Validation Happens at Service Layer:**
- All validation before any database operation
- Multiple validators called in sequence
- Each validator can raise HTTPException independently

**Transaction-Like Semantics:**
- NetBox is the database - no local transactions
- Operations must be atomic (single write) or idempotent (can retry)

---

*Convention analysis: 2026-03-27*
