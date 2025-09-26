# 🌐 VLAN Segment Manager

![Docker Build](https://github.com/Roi12345/vlan-manager/workflows/Build%20and%20Push%20Docker%20Image/badge.svg)
![Tests](https://github.com/Roi12345/vlan-manager/workflows/Test%20and%20Validate/badge.svg)
![Local Build](https://github.com/Roi12345/vlan-manager/workflows/Build%20Local%20Podman%20Images/badge.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-v2.4.0-green.svg)

A modern, containerized VLAN segment management system built with FastAPI and MongoDB. Features a responsive web UI with dark mode, RESTful API, automated CI/CD pipeline, and deployment options for both air-gapped environments and Kubernetes/OpenShift.

## ✨ Features

- 🔧 **VLAN Management**: Allocate and release VLAN segments for clusters
- 🏢 **Multi-Site Support**: Manage VLANs across multiple sites
- 🛡️ **Site IP Validation**: Automatic validation of IP prefixes per site (configurable)
- 🌐 **Web Interface**: Modern, responsive UI with dark/light mode toggle
- 🔍 **Advanced Filtering**: Filter segments by site and allocation status
- 📊 **Export Capabilities**: CSV/Excel export with filtering support  
- 🚀 **RESTful API**: Complete API for automation and integration
- 📈 **Real-time Statistics**: Site utilization and availability metrics
- 📋 **Bulk Operations**: CSV import for mass segment creation
- 📁 **Log Viewing**: Built-in log file viewer via web interface
- 🐳 **Container Ready**: Docker/Podman deployment with health checks
- ☸️ **Kubernetes/OpenShift**: Complete Helm chart included
- 🔒 **Air-Gapped Deployment**: Podman save/load workflow for isolated networks
- 🚀 **CI/CD Pipeline**: Automated Docker builds with version management and artifact generation

## 🏗️ Architecture

```
├── src/                    # Application source code
│   ├── api/               # FastAPI routes and endpoints
│   ├── config/            # Configuration and logging setup
│   ├── database/          # MongoDB connection and operations
│   ├── models/            # Pydantic data models
│   ├── services/          # Business logic layer
│   └── utils/             # Utilities and validators
├── static/                # Web UI assets
│   ├── css/               # Stylesheets (with dark mode)
│   ├── js/                # Frontend JavaScript
│   └── html/              # HTML templates
├── deploy/                # Deployment configurations
│   ├── scripts/           # Podman deployment scripts
│   ├── helm/              # Kubernetes Helm chart
│   └── podman/            # Container images (generated)
├── backup/                # Legacy code backups
├── Dockerfile             # Container image definition
├── requirements.txt       # Python dependencies
└── main.py               # Application entry point
```

## 🚀 Quick Start

### Option 1: Direct Python Deployment
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
export MONGODB_URL="mongodb://username:password@your-mongo-host:27017/vlan_manager?authSource=admin"
export DATABASE_NAME="vlan_manager"
export SITES="site1,site2,site3"
export SITE_PREFIXES="site1:192,site2:193,site3:194"

# Run application
python main.py
```

### Option 2: Container Deployment
```bash
# Build container image
podman build -t vlan-manager .

# Run with environment variables
podman run -d \
  --name vlan-manager \
  -p 8000:8000 \
  -e MONGODB_URL="mongodb://user:pass@mongo-host:27017/vlan_manager?authSource=admin" \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  vlan-manager
```

### Option 3: Air-Gapped Deployment
```bash
# On connected system - build and save image
./deploy/scripts/build-and-save.sh

# Transfer deploy/podman/vlan-manager-latest.tar to air-gapped system

# On air-gapped system - load and run
cp .env.example .env  # Edit with your MongoDB details
./deploy/scripts/load-and-run.sh
```

## 📊 Web Interface

Access the application at **http://localhost:8000**

### Main Features:
- **Dashboard**: Real-time statistics per site with utilization charts
- **Segment Management**: Create, view, and delete VLAN segments with IP validation
- **Advanced Filtering**: Filter segments by site and allocation status
- **Data Export**: Export filtered data to CSV or Excel formats
- **VLAN Allocation**: Allocate segments to clusters with automatic tracking
- **Site IP Validation**: Automatic validation ensures segments match site IP prefixes
- **Bulk Import**: CSV import for multiple segments
- **Dark Mode**: Toggle between light and dark themes
- **Responsive Design**: Works on desktop, tablet, and mobile

### API Endpoints:
- `GET /api/health` - Health check and status
- `GET /api/sites` - List configured sites
- `GET /api/stats` - Site statistics and utilization
- `GET /api/segments` - List segments with optional filters (`site`, `allocated`)
- `POST /api/segments` - Create new segment (with IP prefix validation)
- `DELETE /api/segments/{id}` - Delete segment
- `POST /api/segments/bulk` - Bulk create segments
- `POST /api/allocate-vlan` - Allocate VLAN to cluster
- `POST /api/release-vlan` - Release VLAN allocation
- `GET /api/export/segments/csv` - Export segments to CSV
- `GET /api/export/segments/excel` - Export segments to Excel  
- `GET /api/export/stats/csv` - Export statistics to CSV
- `GET /api/logs` - View application logs
- `GET /docs` - Interactive API documentation

## ⚙️ Configuration

### Environment Variables
```bash
# MongoDB Connection (Required)
MONGODB_URL="mongodb://username:password@host:port/database?authSource=admin"
DATABASE_NAME="vlan_manager"

# Site Configuration (Required)
SITES="site1,site2,site3"

# Site IP Prefix Validation (Optional)
SITE_PREFIXES="site1:192,site2:193,site3:194"

# Server Configuration (Optional)
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"
```

### Site IP Validation
Configure which IP address ranges are valid for each site:
- **Format**: `"site1:192,site2:193,site3:194"`
- **Default**: Sites default to 192 prefix if not specified
- **Validation**: Ensures segment IPs match site-specific prefixes
- **Example**: site1 only accepts `192.x.x.x/xx`, site2 only accepts `193.x.x.x/xx`

### MongoDB Setup
The application automatically creates comprehensive database indexes on startup for optimal performance:

**Core Indexes:**
- Unique index on `(site, vlan_id)` - Prevents duplicate VLANs per site
- Index on `cluster_name` - Basic allocation queries
- Index on `(site, released)` - Availability queries
- Index on `epg_name` - EPG-based searches

**Optimized Compound Indexes:**
- `(site, cluster_name, vlan_id)` - Perfect for allocation queries with sorting
- `(cluster_name, site, released)` - Existing allocation checks
- `(cluster_name, vlan_id)` - Global filtering with sorting
- `(site, cluster_name, released)` - Statistics calculations

**Timestamp Indexes:**
- `(allocated_at)` - Allocation time queries
- `(released_at)` - Release time queries

## 🚀 CI/CD Pipeline

This project includes a comprehensive GitHub Actions CI/CD pipeline that automatically builds and distributes container images.

### 🔄 Automated Workflows

- **Docker Build Pipeline**: Auto-incremental versioning with Docker Hub publishing
- **Local Podman Build**: Creates downloadable Podman image artifacts  
- **Test & Validation**: Python linting, type checking, and container testing
- **Release Pipeline**: Multi-registry publishing for tagged releases

### 📦 Image Distribution

**Docker Hub Images** (automatically published):
```bash
# Pull latest version
docker pull roi12345/vlan-manager:latest

# Pull specific version
docker pull roi12345/vlan-manager:v2.4.0
```

**Podman Archive Images** (GitHub Actions artifacts):
- Download from Actions tab → "Build Local Podman Images" 
- Extract and run: `./deploy.sh`
- Perfect for air-gapped deployments

### 🏷️ Version Strategy

- **Main branch pushes**: Auto-increment patch version (v1.0.0 → v1.0.1)
- **Develop branch**: Beta versions (v1.0.1-beta.1) 
- **Feature branches**: Branch-specific builds (branch-feature-name-{commit})
- **Releases**: Use tagged version (v2.0.0)

### ⚙️ Setup Instructions

1. **Configure GitHub Secrets** (Repository Settings → Secrets):
   ```
   DOCKER_USERNAME: Roi12345
   DOCKER_PASSWORD: [your-dockerhub-access-token]
   ```

2. **Run the setup script**:
   ```bash
   ./setup-pipeline.sh
   ```

3. **Push to trigger builds**:
   ```bash
   git push origin main  # Triggers auto-versioned build
   ```

See [CI-CD-README.md](CI-CD-README.md) for complete pipeline documentation.

## 🐳 Container Deployment

### Docker/Podman Build
```bash
# Build image
podman build -t vlan-manager .

# Run with custom configuration
podman run -d \
  --name vlan-manager \
  -p 8000:8000 \
  -e MONGODB_URL="your-connection-string" \
  -e DATABASE_NAME="vlan_manager" \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  -v ./logs:/app/logs \
  --restart unless-stopped \
  vlan-manager
```

### Health Checks
Container includes built-in health checks:
- **Endpoint**: `GET /api/health`
- **Interval**: Every 30 seconds
- **Timeout**: 10 seconds
- **Start Period**: 60 seconds

## 🔒 Air-Gapped Deployment

Perfect for isolated networks with external MongoDB access.

### 1. Connected Environment (Build & Save)
```bash
./deploy/scripts/build-and-save.sh [tag]
```
Creates:
- `deploy/podman/vlan-manager-[tag].tar` - Container image
- `deploy/podman/TRANSFER-INSTRUCTIONS.md` - Transfer guide

### 2. Transfer to Air-Gapped Network
Copy these files:
- `vlan-manager-[tag].tar` (container image)
- `load-and-run.sh` (deployment script)
- `.env.example` (configuration template)

### 3. Air-Gapped Environment (Load & Run)
```bash
# Configure environment
cp .env.example .env
vi .env  # Add your MongoDB connection details

# Deploy
./load-and-run.sh [tag]
```

## ☸️ Kubernetes/OpenShift Deployment

Complete Helm chart included for enterprise deployments.

### Prerequisites
- Helm 3.x
- Access to Kubernetes/OpenShift cluster
- Container image in accessible registry

### Installation
```bash
# Basic deployment
helm install vlan-manager ./deploy/helm \
  --set mongodb.secret.url="mongodb://user:pass@mongo:27017/vlan_manager?authSource=admin" \
  --set config.sites="site1,site2,site3" \
  --set config.sitePrefixes="site1:192,site2:193,site3:194"

# Production deployment with custom values
helm install vlan-manager ./deploy/helm -f production-values.yaml
```

### OpenShift Specific
```bash
# Create project
oc new-project vlan-manager

# Deploy
helm install vlan-manager ./deploy/helm \
  --set mongodb.secret.url="mongodb://user:pass@mongodb:27017/vlan_manager?authSource=admin" \
  --set config.sites="site1,site2,site3" \
  --set config.sitePrefixes="site1:192,site2:193,site3:194"

# Expose route
oc expose service vlan-manager
```

### Configuration Options
Edit `deploy/helm/values.yaml`:
- Resource limits/requests
- Scaling configuration (HPA)
- Ingress/Route setup
- Environment variables
- Storage configuration
- Security contexts

## 🔧 Development

### Local Development Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\\Scripts\\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MONGODB_URL="your-connection-string"
export SITES="site1,site2,site3"

# Run in development mode
python main.py
```

### Project Structure Benefits
- **Separation of Concerns**: Clean architecture with distinct layers
- **Testability**: Services and utilities can be easily unit tested
- **Maintainability**: Modular code structure for easy modifications
- **Scalability**: Easy to add new features and endpoints
- **Type Safety**: Full Pydantic model validation throughout

### Adding New Features
1. **Models**: Add Pydantic schemas in `src/models/schemas.py`
2. **Database**: Add operations in `src/utils/database_utils.py`  
3. **Business Logic**: Implement services in `src/services/`
4. **API**: Add endpoints in `src/api/routes.py`
5. **Frontend**: Update UI in `static/` directory

## 📊 Data Models

### Segment Model
```json
{
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
```

### API Request Examples
```bash
# Allocate VLAN
curl -X POST http://localhost:8000/api/allocate-vlan \
  -H "Content-Type: application/json" \
  -d '{"cluster_name": "my-cluster", "site": "site1"}'

# Create Segment
curl -X POST http://localhost:8000/api/segments \
  -H "Content-Type: application/json" \
  -d '{"site": "site1", "vlan_id": 150, "epg_name": "EPG_NEW", "segment": "192.168.150.0/24"}'

# Get Statistics
curl http://localhost:8000/api/stats
```

## 🔍 Troubleshooting

### Common Issues

#### MongoDB Connection Failed
```bash
# Check connectivity
curl http://localhost:8000/api/health

# Verify MongoDB URL format
MONGODB_URL="mongodb://user:pass@host:port/db?authSource=admin"
```

#### Container Won't Start
```bash
# Check logs
podman logs vlan-manager

# Verify environment variables
podman exec vlan-manager env | grep MONGODB
```

#### Port Already in Use
```bash
# Check what's using port 8000
netstat -tlnp | grep :8000

# Use different port
podman run -p 8080:8000 vlan-manager
```

#### Web UI Not Loading
1. Verify container is running: `podman ps`
2. Check port mapping: `0.0.0.0:8000->8000/tcp`
3. Test API directly: `curl http://localhost:8000/api/health`
4. Check browser console for JavaScript errors

### Logs and Monitoring
- **Container logs**: `podman logs vlan-manager`
- **Application logs**: `http://localhost:8000/api/logs`
- **Health status**: `http://localhost:8000/api/health`
- **Metrics**: `http://localhost:8000/api/stats`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/roiblum1/segments_db/issues)
- **Documentation**: This README and inline code documentation
- **API Docs**: http://localhost:8000/docs (when running)

## 🏷️ Version History

- **v2.0.0**: Enhanced validation and filtering features
  - Site-specific IP prefix validation
  - Advanced segment filtering by site and status
  - CSV/Excel export capabilities with filtering
  - Improved error handling and user feedback
  - Enhanced responsive UI design
  - Optimized container image (347MB)

- **v1.0.0**: Initial release with core VLAN management features
  - Web UI with dark mode
  - RESTful API
  - MongoDB integration  
  - Container deployment
  - Air-gapped deployment support
  - Helm chart for Kubernetes/OpenShift