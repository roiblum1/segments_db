#!/bin/bash

# VLAN Manager - Build and Save Container Image
# This script builds the container image and saves it for air-gapped deployment

set -e

PROJECT_NAME="vlan-manager"
IMAGE_NAME="vlan-manager"
IMAGE_TAG="${1:-latest}"
SAVE_DIR="$(dirname "$0")/../images"

echo "🏗️  VLAN Manager - Build and Save Container Image"
echo "=================================================="

# Check if podman is available
if ! command -v podman &> /dev/null; then
    echo "❌ Podman is not installed. Please install podman first."
    exit 1
fi

echo "📋 Configuration:"
echo "   Image: $IMAGE_NAME:$IMAGE_TAG"
echo "   Save Directory: $SAVE_DIR"

# Navigate to project root
cd "$(dirname "$0")/../.."

echo ""
echo "🐳 Building container image..."
podman build -t $IMAGE_NAME:$IMAGE_TAG .

if [ $? -eq 0 ]; then
    echo "✅ Container image built successfully!"
else
    echo "❌ Failed to build container image"
    exit 1
fi

# Create save directory
mkdir -p "$SAVE_DIR"

echo ""
echo "💾 Saving container image to file..."
podman save -o "$SAVE_DIR/${IMAGE_NAME}-${IMAGE_TAG}.tar" $IMAGE_NAME:$IMAGE_TAG

if [ $? -eq 0 ]; then
    echo "✅ Container image saved successfully!"
    
    # Show file info
    echo ""
    echo "📦 Saved image information:"
    echo "   File: $SAVE_DIR/${IMAGE_NAME}-${IMAGE_TAG}.tar"
    echo "   Size: $(du -h "$SAVE_DIR/${IMAGE_NAME}-${IMAGE_TAG}.tar" | cut -f1)"
    
    # Create transfer instructions
    cat > "$SAVE_DIR/TRANSFER-INSTRUCTIONS.md" << EOF
# Transfer Instructions for Air-Gapped Environment

## Files to Transfer
- \`${IMAGE_NAME}-${IMAGE_TAG}.tar\` - Container image
- \`load-and-run.sh\` - Deployment script
- \`.env.example\` - Environment configuration template

## On Connected System (Source)
1. Files have been saved in: \`$SAVE_DIR/\`
2. Copy files to removable media or transfer system

## On Air-Gapped System (Target)
1. Copy files to target system
2. Run: \`chmod +x load-and-run.sh\`
3. Edit environment: \`cp .env.example .env && vi .env\`
4. Deploy: \`./load-and-run.sh\`

## Environment Variables Required
\`\`\`
# NetBox Connection (Required)
NETBOX_URL=https://your-netbox-instance.com
NETBOX_TOKEN=your-api-token-here
NETBOX_SSL_VERIFY=true

# Site Configuration (Required)
SITES=site1,site2,site3
SITE_PREFIXES=site1:192,site2:193,site3:194

# Server Configuration (Optional)
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
LOG_LEVEL=INFO
\`\`\`
EOF
    
    echo ""
    echo "📄 Transfer instructions created: $SAVE_DIR/TRANSFER-INSTRUCTIONS.md"
    
else
    echo "❌ Failed to save container image"
    exit 1
fi

echo ""
echo "🎉 Build and save completed successfully!"
echo "   Transfer the files in '$SAVE_DIR' to your air-gapped environment"