# Network Segment Manager - Air-Gapped OpenShift Deployment Guide

This guide provides complete instructions for deploying the Network Segment Manager in an air-gapped OpenShift environment.

## 🎯 Overview

The Network Segment Manager has been modified for air-gapped deployment with the following features:

- ✅ **No Network Dependencies**: No `apt-update` or internet access required during build/runtime
- ✅ **OpenShift Compatible**: Supports arbitrary UIDs and security context constraints
- ✅ **Multi-Zone Architecture**: Office1, Office2, Office3 zone separation
- ✅ **Persistent Storage**: SQLite database with PVC-backed persistence
- ✅ **Self-Contained**: All dependencies bundled in the image

## 📁 Files Structure

```
segment_db/
├── Dockerfile.airgap           # Air-gapped Dockerfile
├── build-airgap.sh            # Build and export script
├── openshift/                 # OpenShift deployment manifests
│   ├── README.md              # Detailed deployment guide
│   ├── deploy.sh              # Automated deployment script
│   ├── namespace.yaml         # Namespace definition
│   ├── configmap.yaml         # Application configuration
│   ├── pvc.yaml              # Persistent volume claims
│   ├── deployment.yaml        # Main application deployment
│   ├── service.yaml          # ClusterIP service
│   └── route.yaml            # OpenShift route
└── AIRGAP-DEPLOYMENT.md      # This guide
```

## 🏗️ Building the Air-Gapped Image

### Prerequisites
- Docker or Podman installed
- Access to the source code
- Internet connection (for initial build only)

### Build Process

```bash
# Clone/copy the source code
cd segment_db/

# Build and export the air-gapped image
./build-airgap.sh v1.0.0
```

This will create:
- `network-segment-manager-v1.0.0.tar.gz` - Compressed Docker image

### Manual Build (Alternative)

```bash
# Build the image
podman build -f Dockerfile.airgap -t network-segment-manager:v1.0.0 .

# Export for air-gapped deployment
podman save -o network-segment-manager-v1.0.0.tar network-segment-manager:v1.0.0
gzip network-segment-manager-v1.0.0.tar
```

## 🚚 Transferring to Air-Gapped Environment

1. **Copy the compressed image file**:
   ```bash
   scp network-segment-manager-v1.0.0.tar.gz user@airgapped-host:~/
   ```

2. **Copy the deployment manifests**:
   ```bash
   scp -r openshift/ user@airgapped-host:~/segment-manager-deploy/
   ```

## 📦 Loading Image in Air-Gapped Environment

1. **Decompress and load the image**:
   ```bash
   gunzip network-segment-manager-v1.0.0.tar.gz
   podman load -i network-segment-manager-v1.0.0.tar
   ```

2. **Tag for your internal registry**:
   ```bash
   podman tag network-segment-manager:v1.0.0 registry.internal.local/network-segment-manager:v1.0.0
   ```

3. **Push to internal registry**:
   ```bash
   podman push registry.internal.local/network-segment-manager:v1.0.0
   ```

## 🎛️ OpenShift Deployment

### Prerequisites
- OpenShift cluster access
- `oc` CLI tool configured
- Appropriate permissions for creating namespaces, deployments, etc.

### Automated Deployment

```bash
cd openshift/

# Update deployment.yaml with your registry URL
sed -i 's|image: network-segment-manager:latest|image: registry.internal.local/network-segment-manager:v1.0.0|g' deployment.yaml

# Deploy everything
./deploy.sh v1.0.0
```

### Manual Deployment

1. **Create namespace**:
   ```bash
   oc apply -f namespace.yaml
   oc project segment-manager
   ```

2. **Apply configuration and storage**:
   ```bash
   oc apply -f configmap.yaml
   oc apply -f pvc.yaml
   ```

3. **Deploy application**:
   ```bash
   # Update image reference first
   vim deployment.yaml  # Change image to your registry URL
   
   oc apply -f deployment.yaml
   oc apply -f service.yaml
   oc apply -f route.yaml
   ```

4. **Verify deployment**:
   ```bash
   oc get pods -l app=network-segment-manager
   oc logs -l app=network-segment-manager
   ```

## 🔧 Configuration

### Environment Variables
Configure via ConfigMap (`configmap.yaml`):
- `DATABASE_URL`: SQLite database location
- `LOG_LEVEL`: Application logging level
- `DEFAULT_ZONES`: Available office zones
- `CORS_ORIGINS`: CORS policy configuration

### Storage
- **Data**: 5Gi PVC for SQLite database (`/app/data`)
- **Logs**: 2Gi PVC for application logs (`/app/logs`)

### Security
- Runs as non-root user (UID 1000)
- Supports OpenShift's arbitrary UID assignment
- Security Context Constraints compliant
- TLS-terminated route for external access

## 🌐 Accessing the Application

After deployment, get the route URL:
```bash
oc get route segment-manager-route -o jsonpath='{.spec.host}'
```

Or use port forwarding for testing:
```bash
oc port-forward svc/segment-manager-service 8000:8000
```

Access at: `https://your-route-url` or `http://localhost:8000`

## 🏢 Multi-Zone Features

The application supports three zones:
- **Office1**: 10.100.x.x/24 - 10.102.x.x/24
- **Office2**: 10.200.x.x/24 - 10.202.x.x/24  
- **Office3**: 10.50.x.x/24 - 10.52.x.x/24

Each zone maintains separate:
- VLAN ID pools (same VLANs can exist across zones)
- Segment allocation pools
- Cluster assignments
- Usage statistics

## 🔍 Troubleshooting

### Common Issues

1. **Image Pull Errors**:
   ```bash
   # Check if image is available
   oc describe deployment segment-manager
   
   # Verify registry access
   podman pull registry.internal.local/network-segment-manager:v1.0.0
   ```

2. **Permission Issues**:
   ```bash
   # Check security context constraints
   oc get scc
   oc describe scc restricted
   
   # Verify pod security context
   oc describe pod -l app=network-segment-manager
   ```

3. **Storage Issues**:
   ```bash
   # Check PVC status
   oc get pvc
   oc describe pvc segment-manager-data-pvc
   
   # Check available storage classes
   oc get storageclass
   ```

4. **Application Logs**:
   ```bash
   # View application logs
   oc logs -l app=network-segment-manager --tail=100
   
   # Follow logs in real-time
   oc logs -l app=network-segment-manager -f
   ```

### Health Checks

The application provides health endpoints:
- **Health Check**: `GET /health`
- **Metrics**: Application metrics via logs
- **Database**: SQLite database status

## 📈 Scaling Considerations

Current limitations:
- Single instance deployment (SQLite constraint)
- Shared storage for database persistence

For high availability:
1. Migrate to PostgreSQL/MySQL
2. Use external database service
3. Implement database connection pooling
4. Scale horizontally with multiple replicas

## 🔒 Security Best Practices

1. **Network Policies**: Restrict pod-to-pod communication
2. **RBAC**: Use minimal required permissions
3. **Secrets**: Store sensitive data in OpenShift secrets
4. **TLS**: Configure proper TLS certificates for production
5. **Registry**: Use private, secured container registry

## 📞 Support

For issues:
1. Check application logs: `oc logs -l app=network-segment-manager`
2. Verify resource status: `oc get all -l app=network-segment-manager`
3. Check OpenShift events: `oc get events --sort-by=.metadata.creationTimestamp`