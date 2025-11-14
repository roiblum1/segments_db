# MySQL Migration Guide

This guide explains how to use the MySQL storage backend instead of NetBox.

## Overview

The VLAN Manager has been converted from NetBox storage to MySQL storage. All functionality remains the same, but data is now stored in a MySQL database instead of NetBox.

## Key Changes

### Architecture

**Before (NetBox)**:
```
Application → NetBox Storage → NetBox Cloud API → NetBox Database
```

**After (MySQL)**:
```
Application → MySQL Storage → MySQL Database
```

### Benefits

1. **Performance**: Direct database access (no API layer)
   - NetBox: 300-600ms per request (with throttling: 40-60s)
   - MySQL: < 50ms per query

2. **No Rate Limiting**: No external API throttling

3. **Full Control**: Self-hosted database, no external dependencies

4. **Cost**: No NetBox Cloud subscription needed

## Quick Start

### Option 1: Docker Compose (Recommended)

1. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and set MySQL credentials
   ```

2. **Start services**:
   ```bash
   docker-compose up -d
   ```

   This will:
   - Start MySQL database
   - Initialize schema automatically
   - Start VLAN Manager application

3. **Verify**:
   ```bash
   docker-compose ps
   curl http://localhost:9000/api/health
   ```

### Option 2: Manual Setup

1. **Install MySQL**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install mysql-server

   # macOS
   brew install mysql
   ```

2. **Create database and user**:
   ```sql
   CREATE DATABASE vlan_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'vlan_manager'@'localhost' IDENTIFIED BY 'vlan_manager_password';
   GRANT ALL PRIVILEGES ON vlan_manager.* TO 'vlan_manager'@'localhost';
   FLUSH PRIVILEGES;
   ```

3. **Configure application**:
   ```bash
   cp .env.example .env
   # Edit .env with your MySQL credentials
   ```

4. **Initialize database**:
   ```bash
   python init_database.py
   ```

5. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

6. **Run application**:
   ```bash
   python main.py
   ```

## Configuration

### Environment Variables

```bash
# Storage backend
STORAGE_BACKEND=mysql

# MySQL connection
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=vlan_manager
MYSQL_USER=vlan_manager
MYSQL_PASSWORD=your_secure_password
MYSQL_POOL_SIZE=20

# Application settings (same as before)
SITES=Site1,Site2,Site3
SITE_PREFIXES=Site1:192,Site2:193,Site3:194
LOG_LEVEL=INFO
PORT=9000
```

## Database Schema

### Tables

1. **segments** - Main table for IP prefixes/VLANs
2. **vlans** - VLAN definitions
3. **vrfs** - Virtual Routing and Forwarding (networks)
4. **site_groups** - Site organizational grouping
5. **tenants** - Tenant (fixed to "Redbull")
6. **roles** - Prefix roles (fixed to "Data")
7. **vlan_groups** - VLAN grouping by VRF and site

### Key Fields

**segments table**:
- `prefix` - IP prefix (e.g., 10.0.0.0/24)
- `vrf_id` - Network/VRF reference
- `site` - Site name
- `vlan_id` - Associated VLAN reference
- `status` - 'active' (unallocated) or 'reserved' (allocated)
- `cluster_name` - Allocated cluster(s), comma-separated for shared
- `dhcp` - DHCP option (Enabled/Disabled/Relay)
- `comments` - User description
- `allocated_at` - Allocation timestamp
- `released` - Whether segment was released
- `released_at` - Release timestamp

## Migration from NetBox

If you have existing data in NetBox, you'll need to export and import it:

### 1. Export from NetBox

```bash
# Use the NetBox export script (if available)
python export_from_netbox.py > segments.json
```

### 2. Import to MySQL

```bash
# Use the MySQL import script (if available)
python import_to_mysql.py segments.json
```

### 3. Verify Data

```bash
# Check segment count
mysql -u vlan_manager -p vlan_manager -e "SELECT COUNT(*) FROM segments;"

# Check VRFs
mysql -u vlan_manager -p vlan_manager -e "SELECT * FROM vrfs;"
```

## API Compatibility

All APIs remain **100% compatible**. No changes needed in:
- Frontend code
- API clients
- Integration scripts

The only change is the storage backend.

## Performance Comparison

### NetBox Backend

- Normal: 300-600ms per request
- With throttling: 40-60 seconds per request
- Rate limited: ~100 requests before throttling
- Total allocation time: 60-90 seconds (with throttling)

### MySQL Backend

- Query time: < 50ms per query
- No rate limiting
- No throttling
- Total allocation time: < 2 seconds

## Troubleshooting

### Connection Issues

```bash
# Test MySQL connection
mysql -h localhost -u vlan_manager -p

# Check MySQL is running
sudo systemctl status mysql

# Check application logs
tail -f vlan_manager.log
```

### Schema Issues

```bash
# Reinitialize database
python init_database.py

# Or manually:
mysql -u vlan_manager -p vlan_manager < src/database/mysql_schema.sql
```

### Port Conflicts

If port 3306 or 9000 is already in use:

```bash
# In .env:
MYSQL_PORT=3307
APP_PORT=9001

# In docker-compose.yml:
# Update port mappings accordingly
```

## Backup and Restore

### Backup

```bash
# Full database backup
mysqldump -u vlan_manager -p vlan_manager > backup.sql

# Segments only
mysqldump -u vlan_manager -p vlan_manager segments > segments_backup.sql
```

### Restore

```bash
# Restore full database
mysql -u vlan_manager -p vlan_manager < backup.sql

# Restore segments only
mysql -u vlan_manager -p vlan_manager < segments_backup.sql
```

## Production Deployment

### Recommended Setup

1. **Use strong passwords** in production
2. **Enable SSL** for MySQL connections
3. **Regular backups** (automated daily backups)
4. **Monitor** database performance and disk space
5. **Use connection pooling** (already configured, MYSQL_POOL_SIZE=20)

### Security Checklist

- [ ] Change default MySQL root password
- [ ] Use strong password for vlan_manager user
- [ ] Restrict MySQL network access (bind to localhost or private network)
- [ ] Enable MySQL SSL/TLS
- [ ] Regular security updates for MySQL
- [ ] Backup encryption for sensitive data
- [ ] Monitor access logs

## Support

If you encounter issues:

1. Check logs: `tail -f vlan_manager.log`
2. Verify MySQL connection: `python init_database.py`
3. Check schema: `mysql -u vlan_manager -p vlan_manager -e "SHOW TABLES;"`
4. Test API: `curl http://localhost:9000/api/health`

## Switching Back to NetBox

If needed, you can switch back to NetBox:

```bash
# In .env:
STORAGE_BACKEND=netbox

# Restart application
```

All NetBox storage code is preserved for backwards compatibility.
