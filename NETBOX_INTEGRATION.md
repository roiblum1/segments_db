# NetBox Integration

This branch (`feature/netbox`) integrates VLAN Manager with NetBox as the persistent storage backend.

## Overview

Instead of using local JSON files, this version uses **NetBox** (open-source IPAM/DCIM platform) as the database:

- **Your API**: Handles all business logic, allocation rules, site prefix validation, EPG validation
- **NetBox**: Provides persistent storage, REST API, and web UI for viewing/managing data

## Architecture

```
Client → Your VLAN Manager API (FastAPI)
         ↓ (business logic, validation, allocation)
         ↓
         NetBox REST API
         ↓
         NetBox Database (PostgreSQL)
```

### Data Mapping

| VLAN Manager Concept | NetBox Object | Notes |
|---------------------|---------------|-------|
| Segment | IP Prefix | The IP subnet (e.g., 192.168.1.0/24) |
| VLAN ID | VLAN | VLAN definition with ID |
| Site | Site | Location/data center |
| EPG Name | Custom Field on Prefix | Stored as metadata |
| Cluster Name | Custom Field on Prefix | Which cluster allocated it |
| Allocated Status | Custom Field on Prefix | Is it allocated? |
| Allocation Time | Custom Field on Prefix | When was it allocated? |

## Configuration

### Environment Variables

```bash
# NetBox Connection (Required)
NETBOX_URL="https://your-netbox-instance.com"
NETBOX_TOKEN="your-api-token-here"

# NetBox SSL Verification (Optional)
NETBOX_SSL_VERIFY="true"  # Set to false for self-signed certs

# Site Configuration (Required - same as before)
SITES="site1,site2,site3"
SITE_PREFIXES="site1:192,site2:193,site3:194"
```

### Getting a NetBox Token

1. Log into NetBox web UI
2. Go to your user profile (top right)
3. Click "API Tokens"
4. Create a new token with write permissions
5. Copy the token value

## Running with NetBox

### Container Deployment

```bash
# Build image
podman build -t vlan-manager:netbox .

# Run with NetBox backend
podman run -d \
  --name vlan-manager \
  -p 8000:8000 \
  -e NETBOX_URL="https://srcc3192.cloud.netboxapp.com" \
  -e NETBOX_TOKEN="your-token-here" \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  vlan-manager:netbox
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export NETBOX_URL="https://srcc3192.cloud.netboxapp.com"
export NETBOX_TOKEN="your-token-here"
export SITES="site1,site2,site3"
export SITE_PREFIXES="site1:192,site2:193,site3:194"

# Run application
python main.py
```

## Features Preserved

All existing features work exactly the same:

✅ VLAN allocation with your business rules
✅ Site-specific IP prefix validation
✅ EPG name validation
✅ Cluster allocation tracking
✅ Release and re-allocation
✅ CSV/Excel export
✅ Bulk import
✅ Web UI
✅ REST API

## NetBox Benefits

1. **Professional UI**: Browse VLANs and prefixes in NetBox's web interface
2. **Integration**: NetBox integrates with other network tools
3. **Visualization**: Network diagrams, IP utilization charts
4. **Audit Trail**: NetBox tracks all changes with timestamps
5. **Multi-User**: NetBox supports multiple users with permissions
6. **API**: Both your API and NetBox's API are available
7. **Scalability**: PostgreSQL backend scales better than JSON files
8. **Backup**: Standard PostgreSQL backup procedures

## How It Works

### Creating a Segment

1. Client calls your API: `POST /api/segments`
2. Your API validates (site prefix, EPG name, etc.)
3. Your API creates in NetBox:
   - Creates Site in NetBox (if doesn't exist)
   - Creates VLAN in NetBox (if doesn't exist)
   - Creates Prefix in NetBox with custom fields
4. Data is now in NetBox and visible in NetBox UI

### Allocating a VLAN

1. Client calls your API: `POST /api/allocate-vlan`
2. Your API finds available segment (from NetBox)
3. Your API validates allocation rules
4. Your API updates Prefix in NetBox:
   - Sets `cluster_name` custom field
   - Sets `allocated_at` custom field
   - Sets `released = false`
5. Returns allocation to client
6. Allocation visible in NetBox UI

### Viewing in NetBox

After your API creates data, you can view it in NetBox:

1. **IPAM → Prefixes**: See all IP segments with allocation status
2. **IPAM → VLANs**: See all VLANs
3. **Organization → Sites**: See all configured sites
4. **Custom Fields**: See cluster allocations, EPG names, etc.

## Custom Fields in NetBox

The following custom fields should be created in NetBox for optimal functionality:

| Field Name | Object Type | Type | Required |
|-----------|-------------|------|----------|
| epg_name | ipam.prefix | Text | No |
| cluster_name | ipam.prefix | Text | No |
| allocated_at | ipam.prefix | Text | No |
| released | ipam.prefix | Boolean | No |
| released_at | ipam.prefix | Text | No |

**Note**: The application will work without these custom fields, but the metadata won't be stored in NetBox.

## Testing NetBox Connection

```bash
# Health check endpoint shows NetBox status
curl http://localhost:8000/api/health

# Response includes:
{
  "status": "healthy",
  "storage_type": "netbox",
  "netbox_url": "https://...",
  "netbox_version": "4.4.2",
  "netbox_status": "connected",
  ...
}
```

## Troubleshooting

### Invalid Token Error

```json
{"detail": "Invalid token"}
```

**Solution**: Generate a new API token in NetBox with write permissions.

### Connection Refused

**Solution**: Check `NETBOX_URL` is correct and NetBox is accessible from your network.

### SSL Certificate Errors

**Solution**: Set `NETBOX_SSL_VERIFY=false` (not recommended for production).

### Custom Fields Not Showing

**Solution**: Create custom fields in NetBox UI manually (see Custom Fields section above).

## Migration from JSON Storage

If you have existing data in JSON files:

1. **Export existing segments**: `GET /api/export/segments/csv`
2. **Switch to NetBox branch**: `git checkout feature/netbox`
3. **Configure NetBox**: Set environment variables
4. **Import segments**: `POST /api/segments/bulk` with CSV
5. **Verify in NetBox**: Check NetBox UI for data

## Comparison

| Feature | JSON Storage (main) | NetBox Storage (feature/netbox) |
|---------|-------------------|--------------------------------|
| Persistence | Local files | PostgreSQL database |
| Scalability | Limited by file I/O | PostgreSQL scales well |
| Multi-user | File locking | Database transactions |
| UI | Your web UI only | Your web UI + NetBox UI |
| Backup | Copy JSON file | PostgreSQL backup |
| Audit trail | None | NetBox change logging |
| Integration | Standalone | Integrates with NetBox ecosystem |

## Development Notes

- **Storage Layer**: `src/database/netbox_storage.py` implements NetBox storage
- **API Compatibility**: Same API endpoints, same request/response format
- **Business Logic**: All validation and rules remain in your code
- **NetBox**: Used only as persistent storage (not for business logic)

## Future Enhancements

Potential improvements for this branch:

- [ ] Automatic custom field creation in NetBox
- [ ] NetBox webhook integration for real-time updates
- [ ] VLAN group support
- [ ] Tenant isolation
- [ ] IP address allocation within prefixes
- [ ] Device/interface associations
- [ ] Circuit tracking

## Support

- NetBox Documentation: https://docs.netbox.dev/
- NetBox REST API: https://docs.netbox.dev/en/stable/integrations/rest-api/
- pynetbox Library: https://github.com/netbox-community/pynetbox
