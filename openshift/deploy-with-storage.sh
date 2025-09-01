#!/bin/bash

# Network Segment Manager OpenShift Deployment Script with Storage
# This script ensures PVCs are created and bound before deploying the application

set -e

NAMESPACE="segment-manager"
TIMEOUT=300  # 5 minutes timeout for PVC binding

echo "🚀 Starting Network Segment Manager deployment with persistent storage..."

# Function to check if PVC is bound
check_pvc_status() {
    local pvc_name=$1
    local status=$(oc get pvc $pvc_name -n $NAMESPACE -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
    echo $status
}

# Function to wait for PVC to be bound
wait_for_pvc() {
    local pvc_name=$1
    echo "⏳ Waiting for PVC $pvc_name to be bound..."
    
    local count=0
    while [ $count -lt $TIMEOUT ]; do
        local status=$(check_pvc_status $pvc_name)
        
        if [ "$status" = "Bound" ]; then
            echo "✅ PVC $pvc_name is bound"
            return 0
        elif [ "$status" = "Pending" ]; then
            echo "⏳ PVC $pvc_name is still pending... ($count/$TIMEOUT seconds)"
        else
            echo "❌ PVC $pvc_name status: $status"
        fi
        
        sleep 5
        count=$((count + 5))
    done
    
    echo "❌ Timeout waiting for PVC $pvc_name to be bound"
    echo "💡 Check storage classes: oc get storageclass"
    echo "💡 Check PVC details: oc describe pvc $pvc_name -n $NAMESPACE"
    return 1
}

# Step 1: Create namespace
echo "📦 Creating namespace..."
oc apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: $NAMESPACE
  labels:
    name: $NAMESPACE
EOF

# Step 2: Create ConfigMap
echo "⚙️  Creating ConfigMap..."
oc apply -f configmap.yaml

# Step 3: Create PVCs first
echo "💾 Creating Persistent Volume Claims..."
oc apply -f pvc.yaml

# Step 4: Wait for PVCs to be bound
wait_for_pvc "segment-manager-data-pvc"
wait_for_pvc "segment-manager-logs-pvc"

# Step 5: Create Service
echo "🌐 Creating Service..."
oc apply -f service.yaml

# Step 6: Deploy the application
echo "🚀 Deploying application..."
oc apply -f deployment.yaml

# Step 7: Wait for deployment
echo "⏳ Waiting for deployment to be ready..."
oc rollout status deployment/segment-manager -n $NAMESPACE --timeout=300s

# Step 8: Create Route
echo "🔗 Creating Route..."
oc apply -f route.yaml

# Step 9: Get route URL
echo "✅ Deployment completed!"
echo ""
echo "📊 Deployment Status:"
oc get pods -n $NAMESPACE
echo ""
echo "💾 Storage Status:"
oc get pvc -n $NAMESPACE
echo ""
echo "🌐 Access URL:"
ROUTE_HOST=$(oc get route segment-manager -n $NAMESPACE -o jsonpath='{.spec.host}' 2>/dev/null || echo "Route not found")
if [ "$ROUTE_HOST" != "Route not found" ]; then
    echo "https://$ROUTE_HOST"
else
    echo "Route not created. Use port-forward: oc port-forward svc/segment-manager 8000:8000 -n $NAMESPACE"
fi

echo ""
echo "🔍 To troubleshoot storage issues:"
echo "  Check storage classes: oc get storageclass"
echo "  Check PVCs: oc get pvc -n $NAMESPACE"
echo "  Check pod logs: oc logs -f deployment/segment-manager -n $NAMESPACE"