# VLAN Segment Manager - User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [Configuration](#configuration)
3. [Web Interface](#web-interface)
4. [API Reference](#api-reference)
5. [Troubleshooting](#troubleshooting)

## Getting Started

### Prerequisites
- Docker or Podman
- MongoDB database
- Environment variables configured

### Quick Start with Docker
```bash
# Pull the latest image
docker pull roi12345/vlan-manager:latest

# Run the container
docker run -d \
  -p 8000:8000 \
  -e MONGODB_URL="your_mongodb_connection_string" \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  roi12345/vlan-manager:latest
```

### Environment Variables
| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MONGODB_URL` | MongoDB connection string | `mongodb+srv://...` | Yes |
| `DATABASE_NAME` | Database name | `vlan_manager` | No |
| `SITES` | Comma-separated list of sites | `site1,site2,site3` | Yes |
| `SITE_PREFIXES` | Site to IP prefix mapping | `site1:192,site2:193,site3:194` | Yes |

## Configuration

### Site and Prefix Configuration
The application requires each site to have a corresponding IP prefix:

```bash
# Example configuration
SITES="datacenter1,datacenter2,cloud1"
SITE_PREFIXES="datacenter1:192,datacenter2:193,cloud1:10"
```

**Important**: The application will crash on startup if any site lacks a corresponding IP prefix. This is by design to prevent configuration errors.

### Segment Format Requirements
Segments must follow the format: `{site_prefix}.{x}.{y}.0/24`

Examples:
- For site1 (prefix 192): `192.168.1.0/24`
- For site2 (prefix 193): `193.168.2.0/24`

## Web Interface

### Main Dashboard
Access the web interface at `http://localhost:8000`

#### Features:
- **View Segments**: Browse all segments with filtering options
- **Search**: Search by VLAN ID, EPG name, description, or segment
- **Create Segment**: Add new segments with validation
- **Edit Segment**: Modify existing segments
- **Bulk Operations**: Create multiple segments at once
- **Cluster Management**: Assign/release segments to/from clusters

#### Filtering Options:
- **Site**: Filter by specific site
- **Allocation Status**: Show allocated, unallocated, or all segments
- **Search**: Free-text search across multiple fields

#### Segment Management:
1. **Creating Segments**:
   - Select site from dropdown
   - Enter VLAN ID (must be unique per site)
   - Provide EPG name (cannot be empty)
   - Enter network segment (automatically validated)
   - Add optional description

2. **Editing Segments**:
   - Click edit button on any segment
   - Modify any field except allocated segments
   - System prevents VLAN conflicts

3. **Cluster Assignment**:
   - Use cluster field to assign segments
   - Enter comma-separated cluster names
   - Leave empty to release segment

### Bulk Operations
Upload CSV or create multiple segments through the bulk interface:
```csv
site,vlan_id,epg_name,segment,description
site1,100,web-servers,192.168.1.0/24,Web server network
site1,101,db-servers,192.168.2.0/24,Database network
```

## API Reference

### Base URL
All API endpoints are prefixed with `/api`

### Segments Endpoints

#### GET /api/segments
Retrieve segments with optional filtering
```bash
# Get all segments
curl http://localhost:8000/api/segments

# Filter by site
curl http://localhost:8000/api/segments?site=site1

# Filter by allocation status
curl http://localhost:8000/api/segments?allocated=true

# Search segments
curl http://localhost:8000/api/segments/search?q=web&site=site1
```

#### POST /api/segments
Create a new segment
```bash
curl -X POST http://localhost:8000/api/segments \
  -H "Content-Type: application/json" \
  -d '{
    "site": "site1",
    "vlan_id": 100,
    "epg_name": "web-servers",
    "segment": "192.168.1.0/24",
    "description": "Web server network"
  }'
```

#### PUT /api/segments/{id}
Update an existing segment
```bash
curl -X PUT http://localhost:8000/api/segments/507f1f77bcf86cd799439011 \
  -H "Content-Type: application/json" \
  -d '{
    "site": "site1",
    "vlan_id": 100,
    "epg_name": "updated-servers",
    "segment": "192.168.1.0/24",
    "description": "Updated description"
  }'
```

#### PATCH /api/segments/{id}/clusters
Update cluster assignment
```bash
curl -X PATCH http://localhost:8000/api/segments/507f1f77bcf86cd799439011/clusters \
  -H "Content-Type: application/json" \
  -d '{"cluster_names": "cluster1,cluster2"}'
```

#### DELETE /api/segments/{id}
Delete a segment (only if not allocated)
```bash
curl -X DELETE http://localhost:8000/api/segments/507f1f77bcf86cd799439011
```

### Bulk Operations

#### POST /api/segments/bulk
Create multiple segments
```bash
curl -X POST http://localhost:8000/api/segments/bulk \
  -H "Content-Type: application/json" \
  -d '[
    {
      "site": "site1",
      "vlan_id": 100,
      "epg_name": "web-servers",
      "segment": "192.168.1.0/24",
      "description": "Web server network"
    },
    {
      "site": "site1",
      "vlan_id": 101,
      "epg_name": "db-servers",
      "segment": "192.168.2.0/24",
      "description": "Database network"
    }
  ]'
```

### Statistics and Health

#### GET /api/stats
Get system statistics
```bash
curl http://localhost:8000/api/stats
```

#### GET /api/health
Comprehensive health check
```bash
curl http://localhost:8000/api/health
```

Sample health response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.123456",
  "sites": ["site1", "site2", "site3"],
  "database": {
    "connected": true,
    "operations_test": "passed"
  },
  "site_statistics": {
    "site1": {
      "total_segments": 150,
      "allocated_segments": 45,
      "available_segments": 105
    }
  },
  "system_summary": {
    "total_segments": 450,
    "total_allocated": 135,
    "total_available": 315,
    "allocation_percentage": 30.0
  }
}
```

## Troubleshooting

### Common Issues

#### Application Won't Start
**Error**: "CRITICAL CONFIGURATION ERROR: Sites [siteX] are missing IP prefixes!"

**Solution**: Ensure all sites in `SITES` have corresponding prefixes in `SITE_PREFIXES`:
```bash
# Correct configuration
SITES="site1,site2"
SITE_PREFIXES="site1:192,site2:193"
```

#### Database Connection Issues
**Error**: Database connection timeout

**Solutions**:
1. Verify MongoDB URL is correct
2. Check network connectivity
3. Ensure MongoDB allows connections from your IP
4. Verify authentication credentials

#### Validation Errors

**VLAN Already Exists**:
- Each VLAN ID must be unique per site
- Check existing segments before creating new ones

**Invalid Segment Format**:
- Must use format: `{site_prefix}.{x}.{y}.0/24`
- Example: For site with prefix 192: `192.168.1.0/24`

**Empty EPG Name**:
- EPG names cannot be empty or whitespace only
- Provide a meaningful name for the endpoint group

### Health Check Failures
If health checks fail, check:
1. Database connectivity
2. Site configuration
3. MongoDB performance
4. Application logs in `vlan_manager.log`

### Performance Issues
For large deployments:
1. Monitor MongoDB performance
2. Use filtering when querying large datasets
3. Consider database indexing for frequently searched fields
4. Check application logs for slow queries

### Support
- Check application logs: `vlan_manager.log`
- Use health endpoint: `/api/health`
- Enable debug logging by setting log level to DEBUG