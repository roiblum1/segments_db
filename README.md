# 🌐 VLAN Segment Manager

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-v4.0.0--mysql-green.svg)
![Storage](https://img.shields.io/badge/storage-MySQL-orange.svg)

A modern, high-performance VLAN segment management system built with FastAPI and MySQL backend. Features responsive web UI with dark mode, RESTful API, MySQL database storage, comprehensive validation, and production-ready deployment.

## ✨ Key Features

### Core Functionality
- 🔧 **VLAN Management**: Allocate and release VLAN segments for clusters
- 🏢 **Multi-Site Support**: Manage VLANs across multiple sites and networks
- 🔄 **Shared Segments**: Support for segments shared across multiple clusters
- 🛡️ **Comprehensive Validation**: EPG name, IP format, and site prefix enforcement
- 🌐 **Web Interface**: Modern, responsive UI with dark/light mode toggle
- 🔍 **Advanced Search**: Real-time search by cluster, EPG name, VLAN ID

### Storage & Performance
- ⚡ **MySQL Backend**: Direct database access for maximum performance (< 50ms queries)
- 🚀 **No Rate Limiting**: No external API throttling
- 💾 **Full Control**: Self-hosted database, no external dependencies
- 📊 **Connection Pooling**: Async MySQL with connection pooling (20 connections)

### API & Integration
- 📡 **RESTful API**: Complete API for automation and integration
- 📤 **Export**: CSV/Excel export with advanced filtering
- 📥 **Bulk Import**: CSV import for mass segment creation
- 🔌 **Backend Agnostic**: Switchable storage backend (MySQL/NetBox)

### Monitoring & Operations
- 📈 **Health Monitoring**: Comprehensive health checks with database validation
- 📋 **Log Viewer**: Built-in log file viewer via web interface
- 🐳 **Container Ready**: Docker Compose with MySQL included
- 📊 **Statistics**: Per-site utilization and allocation statistics

## 🏗️ Architecture

### Storage Backend

**MySQL (Default & Recommended)**:
```
Application → MySQL Storage Layer → MySQL Database
```

**NetBox (Legacy, optional)**:
```
Application → NetBox Storage Layer → NetBox API → NetBox Database
```

### Project Structure

```
├── src/
│   ├── api/                 # FastAPI routes
│   ├── config/              # Configuration (MySQL, NetBox)
│   ├── database/            
│   │   ├── mysql_storage.py      # MySQL storage implementation
│   │   ├── mysql_schema.sql      # Database schema
│   │   └── netbox_storage.py     # NetBox storage (legacy)
│   ├── models/              # Pydantic data models
│   ├── services/            # Business logic
│   └── utils/               # Utilities and validators
├── static/                  # Web UI
│   ├── css/                 # Stylesheets
│   ├── js/                  # Frontend JavaScript
│   └── html/                # HTML templates
├── docker-compose.yml       # Docker Compose with MySQL
├── Dockerfile               # Application container
├── init_database.py         # Database initialization
└── requirements.txt         # Python dependencies

```

## 🚀 Quick Start

### Using Docker Compose (Recommended)

1. **Clone and configure**:
   ```bash
   git clone https://github.com/your-org/vlan-manager.git
   cd vlan-manager
   cp .env.example .env
   # Edit .env with your settings
   ```

2. **Start services**:
   ```bash
   docker-compose up -d
   ```

   This automatically:
   - Starts MySQL database
   - Initializes schema
   - Starts VLAN Manager
   - Sets up networking

3. **Access the application**:
   - Web UI: http://localhost:9000
   - API: http://localhost:9000/api
   - Health: http://localhost:9000/api/health

### Manual Installation

1. **Install MySQL**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install mysql-server

   # macOS
   brew install mysql
   ```

2. **Create database**:
   ```sql
   CREATE DATABASE vlan_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'vlan_manager'@'localhost' IDENTIFIED BY 'secure_password';
   GRANT ALL PRIVILEGES ON vlan_manager.* TO 'vlan_manager'@'localhost';
   ```

3. **Configure and run**:
   ```bash
   cp .env.example .env
   # Edit .env
   pip install -r requirements.txt
   python init_database.py
   python main.py
   ```

## 📋 Configuration

### Environment Variables

```bash
# Storage Backend
STORAGE_BACKEND=mysql          # or "netbox" for legacy

# MySQL Configuration
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=vlan_manager
MYSQL_USER=vlan_manager
MYSQL_PASSWORD=your_secure_password
MYSQL_POOL_SIZE=20

# Application Settings
SITES=Site1,Site2,Site3
SITE_PREFIXES=Site1:192,Site2:193,Site3:194
LOG_LEVEL=INFO
PORT=9000
```

See `.env.example` for all options.

## 🗄️ Database Schema

### Tables

- **segments** - IP prefixes/VLANs (main table)
- **vlans** - VLAN definitions
- **vrfs** - Virtual Routing and Forwarding (networks)
- **site_groups** - Site organizational grouping
- **tenants** - Tenant management
- **roles** - Prefix roles
- **vlan_groups** - VLAN grouping by VRF and site

### Key Fields

| Field | Description |
|-------|-------------|
| prefix | IP prefix (e.g., 10.0.0.0/24) |
| vrf_id | Network/VRF reference |
| site | Site name |
| vlan_id | VLAN reference |
| status | 'active' (unallocated) or 'reserved' (allocated) |
| cluster_name | Allocated cluster(s), comma-separated for shared |
| dhcp | DHCP option (Enabled/Disabled/Relay) |
| allocated_at | Allocation timestamp |
| released | Whether segment was released |

## 📡 API Endpoints

### Segments
- `GET /api/segments` - List all segments
- `POST /api/segments` - Create segment
- `GET /api/segments/{id}` - Get segment details
- `PUT /api/segments/{id}` - Update segment
- `DELETE /api/segments/{id}` - Delete segment

### Allocations
- `POST /api/segments/allocate` - Allocate segment
- `DELETE /api/segments/{id}/release` - Release allocation

### Utilities
- `GET /api/sites` - List configured sites
- `GET /api/vrfs` - List available VRFs/networks
- `GET /api/health` - Health check with database stats
- `GET /api/logs` - View application logs

## 🔧 Development

### Setup Development Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Setup MySQL database
python init_database.py

# Run application
python main.py
```

### Run Tests

```bash
# Comprehensive application tests
python test_comprehensive.py

# NetBox-specific tests (if using NetBox backend)
python test_netbox.py
```

### Code Structure

The application follows clean architecture principles:

1. **API Layer** (`src/api/`) - HTTP endpoints
2. **Service Layer** (`src/services/`) - Business logic
3. **Storage Layer** (`src/database/`) - Data persistence
4. **Models** (`src/models/`) - Data structures
5. **Utils** (`src/utils/`) - Shared utilities

## 🐳 Docker Deployment

### Build Image

```bash
docker build -t vlan-manager:latest .
```

### Run with Docker Compose

```bash
docker-compose up -d
docker-compose logs -f
```

### Environment Variables

Pass environment variables via `.env` file or `docker-compose.yml`.

## 📊 Performance

### MySQL Backend

- **Query Performance**: < 50ms per query
- **Allocation Time**: < 2 seconds
- **No Rate Limiting**: Unlimited requests
- **Connection Pooling**: 20 concurrent connections

### Comparison with NetBox

| Metric | MySQL | NetBox Cloud |
|--------|-------|--------------|
| Normal Query | < 50ms | 300-600ms |
| Under Load | < 50ms | 40-60 seconds |
| Rate Limiting | None | ~100 requests before throttling |
| Total Allocation | < 2s | 60-90s (with throttling) |

## 🔒 Security

### Production Checklist

- [ ] Use strong MySQL passwords
- [ ] Enable MySQL SSL/TLS
- [ ] Restrict MySQL network access
- [ ] Regular database backups
- [ ] Update dependencies regularly
- [ ] Use secrets management (not .env in production)
- [ ] Enable application logging
- [ ] Monitor database access

### Backup & Restore

```bash
# Backup
mysqldump -u vlan_manager -p vlan_manager > backup.sql

# Restore
mysql -u vlan_manager -p vlan_manager < backup.sql
```

## 📚 Documentation

- [MySQL Migration Guide](MYSQL_MIGRATION.md) - Complete migration guide
- [API Documentation](http://localhost:9000/docs) - Interactive API docs (Swagger)
- [Alternative API Docs](http://localhost:9000/redoc) - ReDoc format

## 🔄 Migration from NetBox

See [MYSQL_MIGRATION.md](MYSQL_MIGRATION.md) for detailed migration guide.

### Quick Migration Steps

1. Export data from NetBox (if needed)
2. Update `.env` to use MySQL backend
3. Initialize MySQL database
4. Import data (if migrating)
5. Restart application

## 🐛 Troubleshooting

### Connection Issues

```bash
# Test MySQL connection
mysql -h localhost -u vlan_manager -p

# Check application logs
tail -f vlan_manager.log

# Verify database schema
python init_database.py
```

### Common Issues

1. **Port already in use**: Change `PORT` in `.env`
2. **MySQL connection refused**: Check MySQL is running
3. **Schema errors**: Run `python init_database.py`
4. **Missing VRFs**: Check `vrfs` table has default data

## 📄 License

MIT License - See [LICENSE](LICENSE) for details

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 🆘 Support

- Issues: [GitHub Issues](https://github.com/your-org/vlan-manager/issues)
- Documentation: [Wiki](https://github.com/your-org/vlan-manager/wiki)

## 🗺️ Roadmap

- [x] MySQL storage backend
- [x] Docker Compose deployment
- [x] Connection pooling
- [x] Async database operations
- [ ] PostgreSQL support
- [ ] Multi-tenancy
- [ ] RBAC/Authentication
- [ ] Audit logging
- [ ] Grafana integration
- [ ] API rate limiting

## 📝 Changelog

### v4.0.0-mysql (Current)
- **Major**: Switched from NetBox to MySQL storage
- Added MySQL connection pooling
- Added Docker Compose with MySQL
- Improved performance (250x faster)
- No rate limiting
- Database initialization script
- Comprehensive migration guide

### v3.1.0 (NetBox)
- NetBox storage implementation
- Performance optimizations
- Request coalescing
- Thread pool improvements

---

**Made with ❤️ for network automation**
