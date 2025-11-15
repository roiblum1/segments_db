# 🌐 VLAN Manager

A modern, high-performance network VLAN allocation and management system with MySQL backend, designed for multi-site environments.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green.svg)](https://fastapi.tiangolo.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-orange.svg)](https://www.mysql.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## ✨ Features

- **🚀 High Performance**: MySQL backend with connection pooling and intelligent caching (5-second TTL)
- **🔄 Dynamic VLAN Allocation**: Automatic segment assignment for clusters across multiple sites
- **✅ Comprehensive Validation**: IP overlap detection, subnet validation, and site-specific prefix enforcement
- **🌍 Multi-Site Support**: Manage VLANs across multiple data center locations
- **📊 Real-Time Statistics**: Live usage metrics and allocation tracking
- **🔍 Advanced Search**: Search by cluster name, EPG, VLAN ID, or network segment
- **📤 Data Export**: Export to CSV and Excel formats
- **🐳 Docker Ready**: Full Docker Compose setup with health checks
- **🎨 Modern UI**: Clean, responsive web interface with dark mode support

## 📋 Table of Contents

- [Architecture](#-architecture)
- [Requirements](#-requirements)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [API Documentation](#-api-documentation)
- [Database Schema](#-database-schema)
- [Development](#-development)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Troubleshooting](#-troubleshooting)

## 🏗️ Architecture

```
┌─────────────────┐
│   Web UI        │
│  (HTML/CSS/JS)  │
└────────┬────────┘
         │
┌────────▼────────┐
│   FastAPI       │
│   Application   │
├─────────────────┤
│ - Routes        │
│ - Services      │
│ - Validation    │
└────────┬────────┘
         │
┌────────▼────────┐
│  MySQL 8.0      │
│   Database      │
├─────────────────┤
│ - segments      │
│ - vlans         │
│ - vlan_groups   │
│ - site_groups   │
└─────────────────┘
```

## 📦 Requirements

- **Python**: 3.11+
- **MySQL**: 8.0+
- **Docker** (optional): 20.10+ with Docker Compose
- **OS**: Linux, macOS, or Windows with WSL2

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone <repository-url>
cd segments_2

# 2. Create environment file
cp .env.example .env
# Edit .env with your configuration

# 3. Start services
podman-compose up -d
# or
docker-compose up -d

# 4. Access the application
open http://localhost:9000
```

### Option 2: Local Development

```bash
# 1. Install dependencies
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Setup MySQL
mysql -u root -p < src/database/mysql_schema.sql

# 3. Configure environment
cp .env.example .env
# Edit .env with your MySQL credentials

# 4. Run the application
python main.py
```

## ⚙️ Configuration

### Environment Variables

All configuration is managed through the `.env` file. Key variables:

#### MySQL Configuration
```bash
MYSQL_ROOT_PASSWORD=root_password    # Root password for MySQL container
MYSQL_HOST=localhost                 # MySQL server hostname
MYSQL_PORT=3306                      # MySQL server port
MYSQL_DATABASE=vlan_manager          # Database name
MYSQL_USER=vlan_manager              # Database user
MYSQL_PASSWORD=vlan_manager_password # Database password
MYSQL_POOL_SIZE=20                   # Connection pool size
```

#### Site Configuration
```bash
SITES=Site1,Site2,Site3                           # Comma-separated site names
SITE_PREFIXES=Site1:192,Site2:193,Site3:194      # Site IP prefix mapping
```

**Note**: Each site must have a corresponding prefix. Example:
- Site1 uses `192.1.x.x` addresses
- Site2 uses `193.1.x.x` addresses
- Site3 uses `194.1.x.x` addresses

#### Application Configuration
```bash
STORAGE_BACKEND=mysql                # Backend: "mysql" (recommended)
HOST=0.0.0.0                         # Server bind address
PORT=9000                            # Server port
LOG_LEVEL=INFO                       # Logging level
ENVIRONMENT=production               # Environment: development|production
```

### Docker Configuration

The `docker-compose.yml` includes:
- **MySQL 8.0** with automatic schema initialization
- **Application container** with health checks
- **Persistent volumes** for database data
- **Bridge network** for service communication

## 📚 API Documentation

### Base URL
```
http://localhost:9000/api
```

### Endpoints

#### Segments

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/segments` | List all segments (optional filters: `site`, `allocated`) |
| `GET` | `/segments/{id}` | Get segment by ID |
| `GET` | `/segments/search?q={query}` | Search segments |
| `POST` | `/segments` | Create new segment |
| `PUT` | `/segments/{id}` | Update segment (all fields including IP) |
| `DELETE` | `/segments/{id}` | Delete segment |

#### Allocation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/allocate-vlan` | Allocate segment to cluster |
| `POST` | `/release-vlan` | Release segment allocation |

#### Statistics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/stats` | Get allocation statistics |
| `GET` | `/health` | Health check with MySQL status |

### Example API Calls

#### Create Segment
```bash
curl -X POST http://localhost:9000/api/segments \
  -H "Content-Type: application/json" \
  -d '{
    "site": "Site1",
    "vlan_id": 100,
    "epg_name": "EPG_PROD_01",
    "segment": "192.1.1.0/24",
    "dhcp": true,
    "description": "Production network"
  }'
```

#### Update Segment (Including IP)
```bash
curl -X PUT http://localhost:9000/api/segments/1 \
  -H "Content-Type: application/json" \
  -d '{
    "site": "Site1",
    "vlan_id": 100,
    "epg_name": "EPG_PROD_01",
    "segment": "192.1.50.0/24",
    "dhcp": true,
    "description": "Updated network"
  }'
```

#### Allocate VLAN
```bash
curl -X POST http://localhost:9000/api/allocate-vlan \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "prod-cluster-01",
    "site": "Site1"
  }'
```

## 🗄️ Database Schema

### Tables

#### segments
Stores network segments with allocation status.

| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| prefix | VARCHAR(50) | Network segment (e.g., 192.1.1.0/24) |
| site | VARCHAR(50) | Site name |
| vlan_id | INT | Foreign key to vlans table |
| cluster_name | VARCHAR(255) | Allocated cluster (NULL if available) |
| status | ENUM | active, reserved, deprecated |
| dhcp | BOOLEAN | DHCP enabled |
| comments | TEXT | Description |
| allocated_at | TIMESTAMP | Allocation timestamp |
| released | BOOLEAN | Release flag |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

#### vlans
VLAN definitions per site.

| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| vlan_id | INT | VLAN number (1-4094) |
| name | VARCHAR(255) | EPG name |
| vlan_group_id | INT | Foreign key to vlan_groups |
| tenant_id | INT | Foreign key to tenants |
| status | ENUM | active, reserved, deprecated |

## 🛠️ Development

### Project Structure
```
segments_2/
├── src/
│   ├── api/              # FastAPI routes
│   ├── config/           # Configuration management
│   ├── database/         # MySQL storage and schema
│   ├── models/           # Pydantic models
│   ├── services/         # Business logic
│   └── utils/            # Utilities and validators
├── static/
│   ├── css/              # Stylesheets
│   ├── html/             # Web pages
│   └── js/               # Frontend JavaScript
├── tests/                # Test suite
├── docker-compose.yml    # Docker orchestration
├── Dockerfile            # Application container
├── requirements.txt      # Python dependencies
└── main.py              # Application entry point
```

### Running Locally

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python main.py

# Run with auto-reload
uvicorn src.app:app --host 0.0.0.0 --port 9000 --reload
```

## 🧪 Testing

### Run Test Suite

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_comprehensive.py

# Run with verbose output
pytest -v
```

### Manual Testing

The application includes a comprehensive manual test script:

```bash
# Make executable
chmod +x test_comprehensive.py

# Run tests
./test_comprehensive.py
```

## 🚢 Deployment

### Production Deployment

```bash
# 1. Update .env for production
ENVIRONMENT=production
LOG_LEVEL=WARNING
MYSQL_PASSWORD=<strong-password>

# 2. Build and deploy
docker-compose build --no-cache
docker-compose up -d

# 3. Check health
curl http://localhost:9000/api/health

# 4. View logs
docker-compose logs -f app
```

### Health Checks

The application includes built-in health checks:
- **Application**: `http://localhost:9000/api/health`
- **MySQL Connection**: Verified in health response
- **Docker**: Container health checks every 30 seconds

### Monitoring

Key metrics available via `/api/stats`:
- Total segments per site
- Allocation utilization percentage
- Available vs. allocated segments
- VLAN usage statistics

## 🔧 Troubleshooting

### Common Issues

#### MySQL Connection Failed
```bash
# Check MySQL is running
docker-compose ps mysql

# Check logs
docker-compose logs mysql

# Test connection
mysql -h localhost -u vlan_manager -p
```

#### Cache Issues
- Cache TTL is 5 seconds
- Updates visible within 5-10 seconds
- Restart app to clear cache immediately: `docker-compose restart app`

#### Port Already in Use
```bash
# Change port in .env
APP_PORT=9001

# Restart services
docker-compose down && docker-compose up -d
```

### Debug Mode

Enable debug logging:
```bash
# In .env
LOG_LEVEL=DEBUG

# Restart
docker-compose restart app

# View logs
docker-compose logs -f app
```

## 📝 Features in Detail

### Segment IP Update
You can now update segment IP addresses directly through the UI or API. The system validates:
- No overlap with existing segments
- Correct IP format and subnet mask
- Site-specific prefix requirements
- No reserved IP usage

### Validation Rules
- **IP Overlap**: Prevents overlapping network segments
- **Site Prefixes**: Enforces site-specific IP ranges (e.g., Site1 = 192.x.x.x)
- **VLAN Uniqueness**: Prevents duplicate VLANs per site
- **Subnet Validation**: Ensures valid CIDR notation
- **Reserved IPs**: Blocks 0.0.0.0, 127.x.x.x, etc.

### Caching Strategy
- **TTL**: 5 seconds for segment cache
- **Invalidation**: Automatic on create/update/delete
- **Autocommit**: Immediate MySQL commits for data consistency

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Support

For issues, questions, or suggestions, please open an issue on GitHub.

---

**Built with ❤️ using FastAPI, MySQL, and modern web technologies**
