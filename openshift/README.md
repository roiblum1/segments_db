# Network Segment Manager - Air-Gapped OpenShift Deployment

This directory contains all the necessary files to deploy the Network Segment Manager in an air-gapped OpenShift environment.

## Prerequisites

- OpenShift cluster with appropriate permissions
- Docker/Podman for building the image
- `oc` CLI tool configured and logged in
- Air-gapped image registry access

## Air-Gapped Image Build

### 1. Build the Air-Gapped Image

```bash
# From the project root directory
docker build -f Dockerfile.airgap -t network-segment-manager:v1.0.0 .

# Or with Podman
podman build -f Dockerfile.airgap -t network-segment-manager:v1.0.0 .
```

### 2. Tag and Push to Air-Gapped Registry

```bash
# Tag for your air-gapped registry
docker tag network-segment-manager:v1.0.0 your-registry.local/network-segment-manager:v1.0.0

# Push to air-gapped registry
docker push your-registry.local/network-segment-manager:v1.0.0
```

## Deployment Files

- `namespace.yaml` - Creates the segment-manager namespace
- `configmap.yaml` - Application configuration
- `pvc.yaml` - Persistent volume claims for data and logs
- `deployment.yaml` - Main application deployment
- `service.yaml` - ClusterIP service
- `route.yaml` - OpenShift route for external access
- `deploy.sh` - Automated deployment script

## Manual Deployment

### 1. Create Namespace

```bash
oc apply -f openshift/namespace.yaml
oc project segment-manager
```

### 2. Apply Configuration

```bash
oc apply -f openshift/configmap.yaml
```

### 3. Create Storage

```bash
oc apply -f openshift/pvc.yaml
```

### 4. Deploy Application

Update the image reference in `deployment.yaml` to point to your air-gapped registry:

```yaml
image: your-registry.local/network-segment-manager:v1.0.0
```

Then deploy:

```bash
oc apply -f openshift/deployment.yaml
oc apply -f openshift/service.yaml
oc apply -f openshift/route.yaml
```

## Automated Deployment

Use the deployment script for automated setup:

```bash
cd openshift/
./deploy.sh v1.0.0
```

## Air-Gapped Considerations

### Image Features
- ✅ No `apt-get update` or network calls during runtime
- ✅ All dependencies bundled in the image
- ✅ OpenShift security compliance
- ✅ Arbitrary UID support
- ✅ Non-root user execution
- ✅ No external health check dependencies

### OpenShift Security Features
- ✅ Security Context Constraints (SCC) compliant
- ✅ Read-only root filesystem compatible
- ✅ Runs as non-root user
- ✅ Supports arbitrary UIDs
- ✅ Proper file permissions for group access

## Monitoring and Troubleshooting

### Check Application Status

```bash
# View pods
oc get pods -l app=network-segment-manager

# View logs
oc logs -l app=network-segment-manager

# Describe deployment
oc describe deployment segment-manager
```

### Access the Application

```bash
# Get route URL
oc get route segment-manager-route

# Port forward for testing
oc port-forward svc/segment-manager-service 8000:8000
```

### Database and Storage

The application uses SQLite with persistent storage:
- Database: `/app/data/segments.db`
- Logs: `/app/logs/`

Data persists across pod restarts via PersistentVolumeClaims.

## Configuration

Application configuration is managed via the ConfigMap (`configmap.yaml`). Key settings:

- `DATABASE_URL`: SQLite database location
- `LOG_LEVEL`: Logging verbosity
- `DEFAULT_ZONES`: Available office zones
- `CORS_ORIGINS`: CORS policy for web UI

## Security

### Container Security
- Runs as non-root user (UID 1000)
- Uses minimal base image (python:3.11-slim)
- No unnecessary packages installed
- Supports OpenShift's arbitrary UID assignment

### Network Security
- ClusterIP service (internal access only)
- TLS-terminated route for external access
- CORS policy configurable

## Scaling

The application is designed to run as a single instance due to SQLite usage. For high availability:

1. Consider migrating to PostgreSQL
2. Use shared storage for database
3. Implement proper database migration handling

## Support

For issues or questions, check:
1. Pod logs: `oc logs -l app=network-segment-manager`
2. Events: `oc get events --sort-by=.metadata.creationTimestamp`
3. Resource status: `oc get all -l app=network-segment-manager`