# API Usage Guide

Complete guide for using the VLAN Manager API with NetBox integration.

## Quick Start

### 1. Start the API Server

```bash
# Local development
python main.py

# Or with uvicorn
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

API will be available at: `http://localhost:8000`

### 2. Access API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Create Segment

**Endpoint**: `POST /api/segments`

**Request Body**:
```json
{
  "site": "site1",
  "vlan_id": 100,
  "epg_name": "PROD_WEB_EPG",
  "segment": "192.168.100.0/24",
  "description": "DHCP Pool: 192.168.100.10-250 | Gateway: 192.168.100.1 | Environment: Production"
}
```

**Description Field Examples**:
```json
// DHCP enabled segment
"description": "DHCP Pool: 192.168.1.10-100 | Gateway: 192.168.1.1"

// Static IP segment
"description": "Static IPs Only | Gateway: 192.168.1.1 | DNS: 8.8.8.8, 8.8.4.4"

// DMZ segment
"description": "Firewall Zone: DMZ | Datacenter: DC1 | Rack: A-01"

// Database segment
"description": "Database Subnet | Backup: Enabled | Monitoring: Prometheus"

// With location info
"description": "Production Network | Location: Building A Floor 3"

// With security info
"description": "PCI Compliant Zone | Encryption: Required | Audit: Daily"
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8000/api/segments" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "site1",
    "vlan_id": 100,
    "epg_name": "PROD_WEB_EPG",
    "segment": "192.168.100.0/24",
    "description": "DHCP Pool: 192.168.100.10-250 | Gateway: 192.168.100.1"
  }'
```

**Python Example**:
```python
import requests

response = requests.post(
    "http://localhost:8000/api/segments",
    json={
        "site": "site1",
        "vlan_id": 100,
        "epg_name": "PROD_WEB_EPG",
        "segment": "192.168.100.0/24",
        "description": "DHCP Pool: 192.168.100.10-250 | Gateway: 192.168.100.1"
    }
)

print(response.json())
```

**Response**:
```json
{
  "message": "Segment created",
  "id": "42"
}
```

**NetBox Result**:
- **STATUS**: Active (available for allocation)
- **VLAN**: PROD_WEB_EPG (100)
- **DESCRIPTION**: Your description text
- **COMMENTS**: EPG:PROD_WEB_EPG | RELEASED:False

---

### Allocate VLAN to Cluster

**Endpoint**: `POST /api/allocate-vlan`

**Request Body**:
```json
{
  "cluster_name": "web-cluster-prod-01",
  "site": "site1"
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8000/api/allocate-vlan" \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "web-cluster-prod-01",
    "site": "site1"
  }'
```

**Python Example**:
```python
import requests

response = requests.post(
    "http://localhost:8000/api/allocate-vlan",
    json={
        "cluster_name": "web-cluster-prod-01",
        "site": "site1"
    }
)

result = response.json()
print(f"Allocated VLAN: {result['vlan_id']}")
print(f"EPG: {result['epg_name']}")
print(f"Segment: {result['segment']}")
```

**Response**:
```json
{
  "vlan_id": 100,
  "cluster_name": "web-cluster-prod-01",
  "site": "site1",
  "segment": "192.168.100.0/24",
  "epg_name": "PROD_WEB_EPG",
  "allocated_at": "2025-10-31T15:37:54.965422Z"
}
```

**NetBox Result**:
- **STATUS**: Reserved (allocated to cluster)
- **VLAN**: PROD_WEB_EPG (100)
- **DESCRIPTION**: Cluster: web-cluster-prod-01
- **COMMENTS**: EPG:PROD_WEB_EPG | CLUSTER:web-cluster-prod-01 | ALLOCATED_AT:2025-10-31... | RELEASED:False

**Important**: If you allocate to the same cluster again, you'll get the **same VLAN** (idempotency).

---

### Release VLAN from Cluster

**Endpoint**: `POST /api/release-vlan`

**Request Body**:
```json
{
  "cluster_name": "web-cluster-prod-01",
  "site": "site1"
}
```

**cURL Example**:
```bash
curl -X POST "http://localhost:8000/api/release-vlan" \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "web-cluster-prod-01",
    "site": "site1"
  }'
```

**Python Example**:
```python
import requests

response = requests.post(
    "http://localhost:8000/api/release-vlan",
    json={
        "cluster_name": "web-cluster-prod-01",
        "site": "site1"
    }
)

print(response.json())
```

**Response**:
```json
{
  "message": "VLAN released successfully"
}
```

**NetBox Result**:
- **STATUS**: Active (available again)
- **DESCRIPTION**: Available for allocation (or restored original description)
- **COMMENTS**: ...RELEASED:True | RELEASED_AT:2025-10-31...

---

### Get All Segments

**Endpoint**: `GET /api/segments`

**Query Parameters**:
- `site` (optional): Filter by site (e.g., `site1`)
- `allocated` (optional): Filter by allocation status (`true` or `false`)

**Examples**:

```bash
# Get all segments
curl "http://localhost:8000/api/segments"

# Get only site1 segments
curl "http://localhost:8000/api/segments?site=site1"

# Get only allocated segments
curl "http://localhost:8000/api/segments?allocated=true"

# Get available (not allocated) segments for site1
curl "http://localhost:8000/api/segments?site=site1&allocated=false"
```

**Python Example**:
```python
import requests

# Get all segments
response = requests.get("http://localhost:8000/api/segments")
segments = response.json()

# Get available segments for site1
response = requests.get(
    "http://localhost:8000/api/segments",
    params={"site": "site1", "allocated": False}
)
available = response.json()

print(f"Total segments: {len(segments)}")
print(f"Available in site1: {len(available)}")
```

---

### Search Segments

**Endpoint**: `GET /api/segments/search`

**Query Parameters**:
- `q` (required): Search query
- `site` (optional): Filter by site
- `allocated` (optional): Filter by allocation status

Search looks in: cluster name, EPG name, VLAN ID, description, segment

**Examples**:

```bash
# Search for cluster name
curl "http://localhost:8000/api/segments/search?q=web-cluster"

# Search for EPG
curl "http://localhost:8000/api/segments/search?q=PROD_WEB"

# Search for VLAN ID
curl "http://localhost:8000/api/segments/search?q=100"

# Search in site1 only
curl "http://localhost:8000/api/segments/search?q=database&site=site1"
```

**Python Example**:
```python
import requests

# Search for all web clusters
response = requests.get(
    "http://localhost:8000/api/segments/search",
    params={"q": "web-cluster"}
)

segments = response.json()
for seg in segments:
    print(f"VLAN {seg['vlan_id']}: {seg['cluster_name']} - {seg['epg_name']}")
```

---

### Get Segment by ID

**Endpoint**: `GET /api/segments/{segment_id}`

**Example**:

```bash
curl "http://localhost:8000/api/segments/42"
```

**Python Example**:
```python
import requests

response = requests.get("http://localhost:8000/api/segments/42")
segment = response.json()

print(f"Segment: {segment['segment']}")
print(f"VLAN: {segment['vlan_id']}")
print(f"Allocated to: {segment['cluster_name']}")
```

---

### Update Segment

**Endpoint**: `PUT /api/segments/{segment_id}`

**Request Body**:
```json
{
  "site": "site1",
  "vlan_id": 100,
  "epg_name": "PROD_WEB_EPG_UPDATED",
  "segment": "192.168.100.0/24",
  "description": "Updated description with new info"
}
```

**cURL Example**:
```bash
curl -X PUT "http://localhost:8000/api/segments/42" \
  -H "Content-Type: application/json" \
  -d '{
    "site": "site1",
    "vlan_id": 100,
    "epg_name": "PROD_WEB_EPG_UPDATED",
    "segment": "192.168.100.0/24",
    "description": "Updated description"
  }'
```

---

### Delete Segment

**Endpoint**: `DELETE /api/segments/{segment_id}`

**Note**: Can only delete segments that are NOT currently allocated to a cluster.

**Example**:

```bash
curl -X DELETE "http://localhost:8000/api/segments/42"
```

---

### Get Statistics

**Endpoint**: `GET /api/stats`

**Query Parameters**:
- `site` (optional): Get stats for specific site

**Examples**:

```bash
# Get overall statistics
curl "http://localhost:8000/api/stats"

# Get statistics for site1
curl "http://localhost:8000/api/stats?site=site1"
```

**Response**:
```json
{
  "site": "site1",
  "total_segments": 10,
  "allocated": 6,
  "available": 4,
  "utilization": 60.0
}
```

---

## NetBox Integration

### What You See in NetBox UI

When you open NetBox at https://srcc3192.cloud.netboxapp.com/ipam/prefixes/:

```
PREFIX               STATUS       VLAN (EPG)                DESCRIPTION
────────────────────────────────────────────────────────────────────────────
192.168.100.0/24     Active       PROD_WEB_EPG (100)        Available for allocation
192.168.101.0/24     Reserved     PROD_DB_EPG (101)         Cluster: db-cluster-02
```

### NetBox Columns Explained

| Column | Shows | When Allocated | When Available |
|--------|-------|----------------|----------------|
| **PREFIX** | IP network | 192.168.100.0/24 | 192.168.100.0/24 |
| **STATUS** | Allocation state | **Reserved** | **Active** |
| **VLAN** | EPG name + VLAN ID | PROD_WEB_EPG (100) | PROD_WEB_EPG (100) |
| **DESCRIPTION** | Cluster or info | Cluster: web-cluster-01 | Your description text |
| **COMMENTS** | Full metadata | Full timestamps & allocation data | EPG info only |

### Comments Field Format

The comments field contains pipe-separated metadata:

```
EPG:PROD_WEB_EPG | CLUSTER:web-cluster-01 | ALLOCATED_AT:2025-10-31 15:37:54+00:00 | RELEASED:False | RELEASED_AT:None
```

This provides:
- **EPG**: The EPG/application name
- **CLUSTER**: Which cluster owns this segment
- **ALLOCATED_AT**: When it was allocated (ISO timestamp)
- **RELEASED**: Boolean status
- **RELEASED_AT**: When it was released (ISO timestamp)

---

## Complete Workflow Example

### Python Script

```python
import requests
import time

API_BASE = "http://localhost:8000/api"

# 1. Create a new segment
print("1. Creating segment...")
response = requests.post(
    f"{API_BASE}/segments",
    json={
        "site": "site1",
        "vlan_id": 150,
        "epg_name": "MY_APP_EPG",
        "segment": "192.168.150.0/24",
        "description": "DHCP Pool: 192.168.150.10-250 | Gateway: 192.168.150.1"
    }
)
print(f"   Created: {response.json()}")

# 2. List available segments
print("\n2. Listing available segments...")
response = requests.get(f"{API_BASE}/segments", params={"site": "site1", "allocated": False})
available = response.json()
print(f"   Available segments: {len(available)}")

# 3. Allocate VLAN to cluster
print("\n3. Allocating VLAN to cluster...")
response = requests.post(
    f"{API_BASE}/allocate-vlan",
    json={
        "cluster_name": "my-production-cluster",
        "site": "site1"
    }
)
allocation = response.json()
print(f"   Allocated VLAN: {allocation['vlan_id']}")
print(f"   EPG: {allocation['epg_name']}")
print(f"   Segment: {allocation['segment']}")

# 4. Try to allocate again (should return same VLAN)
print("\n4. Testing idempotency...")
response = requests.post(
    f"{API_BASE}/allocate-vlan",
    json={
        "cluster_name": "my-production-cluster",
        "site": "site1"
    }
)
allocation2 = response.json()
print(f"   Second allocation: VLAN {allocation2['vlan_id']}")
print(f"   Same VLAN? {allocation['vlan_id'] == allocation2['vlan_id']}")

# 5. Search for the cluster
print("\n5. Searching for cluster...")
response = requests.get(
    f"{API_BASE}/segments/search",
    params={"q": "my-production-cluster"}
)
results = response.json()
print(f"   Found {len(results)} segments")

# 6. Get statistics
print("\n6. Getting statistics...")
response = requests.get(f"{API_BASE}/stats", params={"site": "site1"})
stats = response.json()
print(f"   Total: {stats['total_segments']}")
print(f"   Allocated: {stats['allocated']}")
print(f"   Utilization: {stats['utilization']}%")

# 7. Release the VLAN
print("\n7. Releasing VLAN...")
response = requests.post(
    f"{API_BASE}/release-vlan",
    json={
        "cluster_name": "my-production-cluster",
        "site": "site1"
    }
)
print(f"   Released: {response.json()}")

print("\n✓ Workflow complete!")
print("\n📋 Check NetBox UI at: https://srcc3192.cloud.netboxapp.com/ipam/prefixes/")
```

---

## Tips and Best Practices

### Description Field Best Practices

Use the description field to store useful network information:

✅ **Good descriptions**:
- `DHCP Pool: 192.168.1.10-250 | Gateway: 192.168.1.1 | Environment: Production`
- `Static IPs Only | Gateway: 192.168.1.1 | DNS: 8.8.8.8, 8.8.4.4`
- `Firewall Zone: DMZ | Datacenter: DC1 | Rack: A-01 | Contact: netadmin@company.com`
- `Database Subnet | Backup: Enabled | Monitoring: Prometheus | SLA: 99.9%`

❌ **Avoid**:
- Empty descriptions
- Just "Production" (not descriptive enough)
- Long paragraphs (use pipe-separated key:value pairs)

### Allocation Best Practices

1. **Always use consistent cluster names**: `prod-web-01`, not mixing `prod_web_01` and `prod-web-01`

2. **Check for existing allocation first**: The API is idempotent, but checking saves a round trip

3. **Release when done**: Don't leave allocated VLANs hanging

4. **Use site parameter**: Always specify the site for multi-site deployments

### NetBox Integration Tips

1. **Use STATUS column for filtering**: In NetBox, filter by "Reserved" to see all allocated segments

2. **Search by cluster name**: NetBox's search works on the description field where cluster names are stored

3. **Check COMMENTS for audit trail**: Full allocation history with timestamps

4. **Use VLAN column**: EPG names are in the VLAN name, easy to spot

---

## Troubleshooting

### "No available segments for site"

**Problem**: All segments are allocated
**Solution**: Release unused allocations or create more segments

### "Invalid IP prefix for site"

**Problem**: IP doesn't match site's prefix (e.g., site1 expects 192.x.x.x)
**Solution**: Check `SITE_PREFIXES` environment variable and use correct prefix

### "VLAN already exists for site"

**Problem**: VLAN ID already used in that site
**Solution**: Use a different VLAN ID or delete the existing segment

### "Segment not found"

**Problem**: Segment ID doesn't exist
**Solution**: Use `GET /api/segments` to list all segments and find the correct ID

---

## Environment Configuration

Required environment variables:

```bash
# Required
SITES="site1,site2,site3"
SITE_PREFIXES="site1:192,site2:193,site3:194"

# NetBox Integration
NETBOX_URL="https://your-netbox-instance.com"
NETBOX_TOKEN="your-api-token-here"

# Optional
LOG_LEVEL="INFO"  # DEBUG, INFO, WARNING, ERROR
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"
```

---

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
python test_complete_api_workflow.py

# Run production tests
python test_production_netbox.py
```

---

## Support

- **API Documentation**: http://localhost:8000/docs
- **NetBox UI**: https://your-netbox-instance.com/ipam/prefixes/
- **Logs**: `tail -f vlan_manager.log`
