#!/bin/bash
# OpenShift deployment script for Network Segment Manager
# Usage: ./deploy.sh [image-tag]

set -e

# Configuration
NAMESPACE="segment-manager"
IMAGE_TAG=${1:-"latest"}
IMAGE_NAME="network-segment-manager:${IMAGE_TAG}"

echo "🚀 Deploying Network Segment Manager to OpenShift"
echo "   Namespace: ${NAMESPACE}"
echo "   Image: ${IMAGE_NAME}"

# Check if logged into OpenShift
if ! oc whoami &>/dev/null; then
    echo "❌ Not logged into OpenShift. Please run 'oc login' first."
    exit 1
fi

# Create namespace
echo "📁 Creating namespace..."
oc apply -f namespace.yaml

# Switch to the namespace
oc project ${NAMESPACE}

# Apply ConfigMap
echo "⚙️  Applying configuration..."
oc apply -f configmap.yaml

# Create PVCs
echo "💾 Creating persistent volumes..."
oc apply -f pvc.yaml

# Wait for PVCs to be bound
echo "⏳ Waiting for PVCs to be bound..."
oc wait --for=condition=Bound pvc/segment-manager-data-pvc --timeout=60s
oc wait --for=condition=Bound pvc/segment-manager-logs-pvc --timeout=60s

# Update deployment with correct image tag
echo "🔄 Updating deployment with image tag: ${IMAGE_TAG}"
sed "s|image: network-segment-manager:latest|image: ${IMAGE_NAME}|g" deployment.yaml > deployment-temp.yaml

# Apply deployment
echo "🚢 Deploying application..."
oc apply -f deployment-temp.yaml

# Clean up temp file
rm deployment-temp.yaml

# Create service
echo "🔌 Creating service..."
oc apply -f service.yaml

# Create route
echo "🛣️  Creating route..."
oc apply -f route.yaml

# Wait for deployment to be ready
echo "⏳ Waiting for deployment to be ready..."
oc rollout status deployment/segment-manager --timeout=300s

# Get the route URL
ROUTE_URL=$(oc get route segment-manager-route -o jsonpath='{.spec.host}')

echo "✅ Deployment completed successfully!"
echo ""
echo "📊 Application Status:"
echo "   Pods: $(oc get pods -l app=network-segment-manager --no-headers | wc -l)"
echo "   Service: $(oc get svc segment-manager-service -o jsonpath='{.spec.clusterIP}'):8000"
echo "   Route: https://${ROUTE_URL}"
echo ""
echo "🔍 Useful commands:"
echo "   View pods: oc get pods"
echo "   View logs: oc logs -l app=network-segment-manager"
echo "   Port forward: oc port-forward svc/segment-manager-service 8000:8000"
echo "   Access app: https://${ROUTE_URL}"