# VLAN Manager Deployment

This directory contains deployment configurations for VLAN Manager in various environments.

## 📁 Structure

```
deploy/
├── scripts/           # Podman deployment scripts
│   ├── build-and-save.sh    # Build and save image for air-gapped transfer
│   ├── load-and-run.sh      # Load and run image in air-gapped environment
│   └── .env.example         # Environment variables template
├── helm/             # Helm chart for OpenShift/Kubernetes
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
└── podman/           # Generated container images (after build)
```

## 🐳 Podman Deployment (Air-Gapped)

### Step 1: Connected Environment (Build & Save)
```bash
# Build and save container image
./deploy/scripts/build-and-save.sh

# This creates:
# - deploy/podman/vlan-manager-latest.tar (container image)
# - deploy/podman/TRANSFER-INSTRUCTIONS.md (guide)
```

### Step 2: Transfer to Air-Gapped Environment
Copy these files to your air-gapped environment:
- `deploy/podman/vlan-manager-latest.tar`
- `deploy/scripts/load-and-run.sh`
- `deploy/scripts/.env.example`

### Step 3: Air-Gapped Environment (Load & Run)
```bash
# Configure environment
cp .env.example .env
vi .env  # Edit with your configuration

# Load and run
./load-and-run.sh
```

### Environment Variables
```bash
# Required - Site configuration
SITES=site1,site2,site3
SITE_PREFIXES=site1:192,site2:193,site3:194

# Optional - Storage configuration
DATA_DIR=/app/data
BACKUP_DIR=/app/backup
HA_MODE=false  # Enable High Availability dual-write mode
```

## ☸️ Helm Deployment (OpenShift/Kubernetes)

### Prerequisites
- Helm 3.x installed
- Access to OpenShift/Kubernetes cluster
- Container image available in registry

### Deploy with Helm
```bash
# Install (single-write mode)
helm install vlan-manager ./deploy/helm \
  --set config.sites="site1,site2,site3" \
  --set config.sitePrefixes="site1:192,site2:193,site3:194" \
  --set persistence.enabled=true

# Install with High Availability mode
helm install vlan-manager ./deploy/helm \
  --set config.sites="site1,site2,site3" \
  --set config.sitePrefixes="site1:192,site2:193,site3:194" \
  --set config.haMode="true" \
  --set persistence.enabled=true

# Upgrade
helm upgrade vlan-manager ./deploy/helm

# Uninstall
helm uninstall vlan-manager
```

### OpenShift Specific
```bash
# Create new project
oc new-project vlan-manager

# Deploy with Helm (HA mode recommended)
helm install vlan-manager ./deploy/helm \
  --set config.sites="site1,site2,site3" \
  --set config.sitePrefixes="site1:192,site2:193,site3:194" \
  --set config.haMode="true" \
  --set persistence.enabled=true

# Create route (OpenShift)
oc expose service vlan-manager
```

### Configuration Options
Edit `deploy/helm/values.yaml` for:
- Resource limits/requests
- Ingress/Route configuration
- Scaling options
- Environment variables
- Storage configuration

## 🔧 Development

### Local Testing
```bash
# Build image locally
podman build -t vlan-manager:dev .

# Run locally (single-write mode)
podman run -d \
  --name vlan-manager-dev \
  -p 8000:8000 \
  -v ./data:/app/data:Z \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  vlan-manager:dev

# Run locally (HA mode)
podman run -d \
  --name vlan-manager-ha-dev \
  -p 8000:8000 \
  -v ./data:/app/data:Z \
  -v ./backup:/app/backup:Z \
  -e HA_MODE="true" \
  -e SITES="site1,site2,site3" \
  -e SITE_PREFIXES="site1:192,site2:193,site3:194" \
  vlan-manager:dev
```

### Custom Configuration
1. Copy and modify `values.yaml` for your environment
2. Use `--values` flag with Helm
3. Override specific values with `--set`

## 🏥 Health Checks

All deployments include health checks:
- **Liveness**: `/api/health` 
- **Readiness**: `/api/health`
- **Startup**: 30 second delay

## 📊 Monitoring

Access application endpoints:
- **Web UI**: `http://your-host:8000`
- **API**: `http://your-host:8000/api`
- **Health**: `http://your-host:8000/api/health`
- **Logs**: `http://your-host:8000/api/logs`

## 🔍 Troubleshooting

### Podman Issues
```bash
# Check container status
podman ps

# View logs
podman logs vlan-manager

# Connect to container
podman exec -it vlan-manager /bin/bash
```

### Kubernetes/OpenShift Issues
```bash
# Check pod status
kubectl get pods -l app.kubernetes.io/name=vlan-manager

# View logs
kubectl logs -l app.kubernetes.io/name=vlan-manager

# Describe pod
kubectl describe pod <pod-name>
```