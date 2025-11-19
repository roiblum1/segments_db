#!/bin/bash

# VLAN Manager - Load and Run Container Image
# This script loads the container image and runs it in air-gapped environment

set -e

PROJECT_NAME="vlan-manager"
IMAGE_NAME="vlan-manager"
IMAGE_TAG="${1:-latest}"
CONTAINER_NAME="vlan-manager"
SCRIPT_DIR="$(dirname "$0")"

echo "🚀 VLAN Manager - Load and Run Container Image"
echo "==============================================="

# Check if podman is available
if ! command -v podman &> /dev/null; then
    echo "❌ Podman is not installed. Please install podman first."
    exit 1
fi

# Check if image file exists
IMAGE_FILE="${IMAGE_NAME}-${IMAGE_TAG}.tar"
if [ ! -f "$IMAGE_FILE" ]; then
    echo "❌ Image file not found: $IMAGE_FILE"
    echo "   Please ensure you have transferred the image file to this directory"
    exit 1
fi

echo "📋 Configuration:"
echo "   Image File: $IMAGE_FILE"
echo "   Container: $CONTAINER_NAME"

# Load environment variables if .env exists
if [ -f .env ]; then
    echo "   Environment: .env file found"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️  No .env file found. Using default environment variables."
    echo "   Create .env from .env.example for production use"
    
    # Set defaults (WARNING: These won't work without NetBox)
    export NETBOX_URL="${NETBOX_URL:-https://your-netbox-instance.com}"
    export NETBOX_TOKEN="${NETBOX_TOKEN:-your-api-token-here}"
    export NETBOX_SSL_VERIFY="${NETBOX_SSL_VERIFY:-true}"
    export SITES="${SITES:-site1,site2,site3}"
    export SITE_PREFIXES="${SITE_PREFIXES:-site1:192,site2:193,site3:194}"
    export SERVER_HOST="${SERVER_HOST:-0.0.0.0}"
    export SERVER_PORT="${SERVER_PORT:-8000}"
    export LOG_LEVEL="${LOG_LEVEL:-INFO}"
fi

echo ""
echo "🔧 Environment Configuration:"
echo "   NetBox URL: $NETBOX_URL"
echo "   Sites: $SITES"
echo "   Site Prefixes: $SITE_PREFIXES"
echo "   NetBox Token: $(echo $NETBOX_TOKEN | sed 's/./*/g')"

echo ""
echo "📥 Loading container image..."
podman load -i "$IMAGE_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Container image loaded successfully!"
else
    echo "❌ Failed to load container image"
    exit 1
fi

# Stop existing container if running
echo ""
echo "🛑 Stopping existing container (if running)..."
podman stop $CONTAINER_NAME 2>/dev/null || true
podman rm $CONTAINER_NAME 2>/dev/null || true

echo ""
echo "🚀 Starting VLAN Manager container..."
podman run -d \
    --name $CONTAINER_NAME \
    --restart unless-stopped \
    -p 8000:8000 \
    -e NETBOX_URL="$NETBOX_URL" \
    -e NETBOX_TOKEN="$NETBOX_TOKEN" \
    -e NETBOX_SSL_VERIFY="$NETBOX_SSL_VERIFY" \
    -e SITES="$SITES" \
    -e SITE_PREFIXES="$SITE_PREFIXES" \
    -e SERVER_HOST="$SERVER_HOST" \
    -e SERVER_PORT="$SERVER_PORT" \
    -e LOG_LEVEL="$LOG_LEVEL" \
    -v ./logs:/app/logs:Z \
    $IMAGE_NAME:$IMAGE_TAG

if [ $? -eq 0 ]; then
    echo "✅ Container started successfully!"
    
    echo ""
    echo "⏳ Waiting for service to start..."
    sleep 15
    
    # Health check
    echo "🏥 Checking service health..."
    if curl -f http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "✅ VLAN Manager is healthy and running!"
        
        echo ""
        echo "🌐 Service Information:"
        echo "   Web UI:  http://localhost:8000"
        echo "   API:     http://localhost:8000/api"
        echo "   Health:  http://localhost:8000/api/health"
        echo "   Logs:    http://localhost:8000/api/logs"
        
        echo ""
        echo "📊 Container Status:"
        podman ps --filter name=$CONTAINER_NAME
        
    else
        echo "❌ Service health check failed"
        echo ""
        echo "📋 Container logs (last 20 lines):"
        podman logs --tail 20 $CONTAINER_NAME
        
        echo ""
        echo "🔍 Troubleshooting:"
        echo "   1. Check NetBox connectivity and URL"
        echo "   2. Verify NETBOX_TOKEN is valid"
        echo "   3. Verify all environment variables are set (especially SITES and SITE_PREFIXES)"
        echo "   4. Check container logs: podman logs $CONTAINER_NAME"
    fi
    
else
    echo "❌ Failed to start container"
    exit 1
fi

echo ""
echo "🎉 Deployment completed!"
echo ""
echo "📋 Useful Commands:"
echo "   View logs:    podman logs $CONTAINER_NAME"
echo "   Stop:         podman stop $CONTAINER_NAME"
echo "   Restart:      podman restart $CONTAINER_NAME"
echo "   Remove:       podman rm $CONTAINER_NAME"