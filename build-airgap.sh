#!/bin/bash
# Build and export air-gapped Docker image for Network Segment Manager
# Usage: ./build-airgap.sh [version]

set -e

# Configuration
VERSION=${1:-"v1.0.0"}
IMAGE_NAME="network-segment-manager"
FULL_IMAGE_NAME="${IMAGE_NAME}:${VERSION}"
TAR_FILE="${IMAGE_NAME}-${VERSION}.tar"

echo "🏗️  Building air-gapped Docker image for Network Segment Manager"
echo "   Version: ${VERSION}"
echo "   Image: ${FULL_IMAGE_NAME}"
echo "   Features: Default user, no apt-update, no service account needed"

# Build the air-gapped image
echo "📦 Building image..."
if command -v podman &> /dev/null; then
    podman build -f Dockerfile.airgap -t ${FULL_IMAGE_NAME} .
    CONTAINER_CMD="podman"
else
    docker build -f Dockerfile.airgap -t ${FULL_IMAGE_NAME} .
    CONTAINER_CMD="docker"
fi

# Export the image for air-gapped deployment
echo "📤 Exporting image to ${TAR_FILE}..."
${CONTAINER_CMD} save -o ${TAR_FILE} ${FULL_IMAGE_NAME}

# Compress the tar file
echo "🗜️  Compressing image..."
gzip -f ${TAR_FILE}
COMPRESSED_FILE="${TAR_FILE}.gz"

# Get file size
FILE_SIZE=$(ls -lh ${COMPRESSED_FILE} | awk '{print $5}')

echo "✅ Air-gapped image ready for deployment!"
echo ""
echo "📊 Build Summary:"
echo "   Image: ${FULL_IMAGE_NAME}"
echo "   File: ${COMPRESSED_FILE}"
echo "   Size: ${FILE_SIZE}"
echo ""
echo "🚀 Deployment Instructions:"
echo "1. Copy ${COMPRESSED_FILE} to your air-gapped environment"
echo "2. Load the image:"
echo "   gunzip ${COMPRESSED_FILE}"
echo "   docker load -i ${TAR_FILE}"
echo "   # or with podman:"
echo "   podman load -i ${TAR_FILE}"
echo ""
echo "3. Tag for your registry:"
echo "   docker tag ${FULL_IMAGE_NAME} your-registry.local/${IMAGE_NAME}:${VERSION}"
echo ""
echo "4. Push to air-gapped registry:"
echo "   docker push your-registry.local/${IMAGE_NAME}:${VERSION}"
echo ""
echo "5. Deploy to OpenShift:"
echo "   cd openshift/"
echo "   ./deploy.sh ${VERSION}"