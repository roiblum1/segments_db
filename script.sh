#!/usr/bin/env bash
#
# update-apiserver-endpoint.sh
#
# Usage:
#   ./update-apiserver-endpoint.sh <hub_cluster_name> <hosted_cluster_name>
#
# Arguments:
#   hub_cluster_name:     Name used with `source o <hub_cluster_name>` for the hub cluster
#   hosted_cluster_name:  Name used with `source o <hosted_cluster_name>` for the hosted cluster
#
# Description:
#   This is a WORKAROUND script to update the API server endpoint on hosted-cluster
#   nodes after changing the kube-apiserver LoadBalancer (e.g., MetalLB -> AKO).
#
# Prerequisites:
#   - SSH key configured for passwordless access to nodes
#   - The `o` helper function/script available (exports kubeconfig for cluster)
#   - oc CLI installed and functional
#
# Safety:
#   - This script ONLY uses read-only 'oc get' commands (no create/delete/patch)
#   - All file modifications are done on the nodes with backups
#
# WARNING:
#   This is a temporary workaround, NOT a supported solution.
#   Nodes should be reinstalled/re-provisioned with the correct endpoint.
#

set -euo pipefail

#-------------------------------------------
# Configuration - SSH Settings
#-------------------------------------------
# SSH user for RHCOS nodes (default: core)
SSH_USER="core"

# Path to SSH private key for node access
# UPDATE THIS PATH to match your environment
SSH_KEY="/path/to/your/ssh/private/key"

# Example paths:
# SSH_KEY="/home/admin/.ssh/id_rsa"
# SSH_KEY="/root/.ssh/ocp_nodes_key"
# SSH_KEY="${HOME}/.ssh/hosted-cluster-key"

#-------------------------------------------
# Terminal colors and formatting
#-------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Get terminal width for clearing lines
TERM_WIDTH=$(tput cols 2>/dev/null || echo 80)

#-------------------------------------------
# Usage function
#-------------------------------------------
usage() {
  cat <<EOF >&2
Usage: $0 <hub_cluster_name> <hosted_cluster_name>

Arguments:
  hub_cluster_name      Name of the hub cluster (for 'source o <name>')
  hosted_cluster_name   Name of the hosted cluster (for 'source o <name>')

Configuration (edit script or export before running):
  SSH_USER              SSH user for node access (default: core)
  SSH_KEY               Path to SSH private key (MUST be configured)

Example:
  # Edit SSH_KEY in script, then run:
  $0 my-hub my-hosted-cluster

  # Or export and run:
  export SSH_KEY=/home/admin/.ssh/id_rsa
  $0 my-hub my-hosted-cluster

Safety Note:
  This script ONLY uses read-only 'oc get' commands.
  No resources are created, deleted, or modified via oc.
EOF
  exit 1
}

#-------------------------------------------
# Logging helpers
#-------------------------------------------
clear_line() {
  # Clear the current line
  printf "\r%-${TERM_WIDTH}s\r" " "
}

log_info() {
  clear_line
  echo -e "${GREEN}[INFO]${NC} $*"
}

log_error() {
  clear_line
  echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_warn() {
  clear_line
  echo -e "${YELLOW}[WARN]${NC} $*" >&2
}

log_progress() {
  # Progress message that stays on same line (no newline)
  echo -ne "\r${CYAN}[....]${NC} $*"
}

log_done() {
  # Complete a progress line with success
  clear_line
  echo -e "${GREEN}[DONE]${NC} $*"
}

log_fail() {
  # Complete a progress line with failure
  clear_line
  echo -e "${RED}[FAIL]${NC} $*"
}

log_skip() {
  # Complete a progress line with skip status
  clear_line
  echo -e "${YELLOW}[SKIP]${NC} $*"
}

#-------------------------------------------
# Validate arguments
#-------------------------------------------
if [[ $# -lt 2 ]]; then
  log_error "Missing required arguments."
  usage
fi

HUB_CLUSTER_NAME="$1"
HOSTED_CLUSTER_NAME="$2"

#-------------------------------------------
# Validate SSH key exists
#-------------------------------------------
if [[ "${SSH_KEY}" == "/path/to/your/ssh/private/key" ]]; then
  log_error "SSH_KEY is not configured!"
  log_error "Please edit the script and set SSH_KEY to your private key path,"
  log_error "or export SSH_KEY before running the script."
  echo
  usage
fi

if [[ ! -f "${SSH_KEY}" ]]; then
  log_error "SSH key not found: ${SSH_KEY}"
  log_error "Please verify the path and ensure the file exists."
  exit 1
fi

if [[ ! -r "${SSH_KEY}" ]]; then
  log_error "SSH key not readable: ${SSH_KEY}"
  log_error "Please check file permissions."
  exit 1
fi

echo -e "${BOLD}${BLUE}"
echo "=============================================="
echo " API Server Endpoint Update Script"
echo "=============================================="
echo -e "${NC}"
echo -e "  Hub cluster:        ${CYAN}${HUB_CLUSTER_NAME}${NC}"
echo -e "  Hosted cluster:     ${CYAN}${HOSTED_CLUSTER_NAME}${NC}"
echo -e "  SSH user:           ${CYAN}${SSH_USER}${NC}"
echo -e "  SSH key:            ${CYAN}${SSH_KEY}${NC}"
echo
echo -e "  ${YELLOW}Safety: This script only uses read-only 'oc get' commands${NC}"
echo

############################################
# Step 1: Get new API endpoint from hub
# NOTE: Only 'oc get' is used - read-only operation
############################################
log_progress "Switching context to hub cluster: ${HUB_CLUSTER_NAME}..."

# shellcheck disable=SC1090
# This assumes you have a script/function `o` that exports kubeconfig
# for the given cluster name. Example: source o my-hub
if ! source o "${HUB_CLUSTER_NAME}" >/dev/null 2>&1; then
  log_fail "Failed to switch context to hub cluster '${HUB_CLUSTER_NAME}'."
  exit 1
fi
log_done "Switched to hub cluster: ${HUB_CLUSTER_NAME}"

HCP_NAMESPACE="hcp-${HOSTED_CLUSTER_NAME}-ocp4-${HOSTED_CLUSTER_NAME}"
log_info "HostedControlPlane namespace: ${HCP_NAMESPACE}"

log_progress "Fetching kube-apiserver Service from hub (read-only)..."

# SAFETY: Using 'oc get' only - read-only operation
if ! oc get svc kube-apiserver -n "${HCP_NAMESPACE}" >/dev/null 2>&1; then
  log_fail "kube-apiserver Service not found in namespace '${HCP_NAMESPACE}'"
  log_error "Please verify the namespace exists and contains the kube-apiserver Service."
  exit 1
fi
log_done "Found kube-apiserver Service in ${HCP_NAMESPACE}"

log_progress "Extracting LoadBalancer address (read-only)..."

# SAFETY: Using 'oc get' only - read-only operation
# Try hostname first (AKO typically provides hostname); if empty, fall back to IP (MetalLB).
NEW_HOSTNAME="$(oc get svc kube-apiserver -n "${HCP_NAMESPACE}" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
NEW_IP="$(oc get svc kube-apiserver -n "${HCP_NAMESPACE}" \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"

LB_ADDR=""
LB_TYPE=""
if [[ -n "${NEW_HOSTNAME}" ]]; then
  LB_ADDR="${NEW_HOSTNAME}"
  LB_TYPE="hostname"
elif [[ -n "${NEW_IP}" ]]; then
  LB_ADDR="${NEW_IP}"
  LB_TYPE="IP"
fi

if [[ -z "${LB_ADDR}" ]]; then
  log_fail "Could not determine LoadBalancer address"
  log_error "Check: oc get svc kube-apiserver -n ${HCP_NAMESPACE} -o yaml"
  exit 1
fi
log_done "LoadBalancer ${LB_TYPE}: ${LB_ADDR}"

NEW_API_ENDPOINT="https://${LB_ADDR}:6443"
echo
echo -e "  ${BOLD}NEW API Endpoint:${NC} ${GREEN}${NEW_API_ENDPOINT}${NC}"
echo

############################################
# Step 2: Switch to hosted cluster & get node IPs
# NOTE: Only 'oc get' is used - read-only operation
############################################
log_progress "Switching context to hosted cluster: ${HOSTED_CLUSTER_NAME}..."

# shellcheck disable=SC1090
if ! source o "${HOSTED_CLUSTER_NAME}" >/dev/null 2>&1; then
  log_fail "Failed to switch context to hosted cluster '${HOSTED_CLUSTER_NAME}'."
  exit 1
fi
log_done "Switched to hosted cluster: ${HOSTED_CLUSTER_NAME}"

log_progress "Fetching node IPs from hosted cluster (read-only)..."

# SAFETY: Using 'oc get' only - read-only operation
NODE_IPS="$(oc get nodes -o wide --no-headers 2>/dev/null | awk '{print $6}')"

if [[ -z "${NODE_IPS}" ]]; then
  log_fail "No node IPs found in hosted cluster '${HOSTED_CLUSTER_NAME}'."
  log_error "Check: oc get nodes -o wide"
  exit 1
fi

# Convert to array for counting and iteration
read -ra NODE_ARRAY <<< "${NODE_IPS}"
NODE_COUNT=${#NODE_ARRAY[@]}

log_done "Found ${NODE_COUNT} node(s)"
echo
echo -e "  ${BOLD}Nodes to update:${NC}"
for ip in "${NODE_ARRAY[@]}"; do
  echo -e "    • ${CYAN}${ip}${NC}"
done
echo

############################################
# Step 3: For each node, SSH and update kubeconfigs
############################################
FAIL_COUNT=0
SUCCESS_COUNT=0
SKIP_COUNT=0
CURRENT_NODE=0

for NODE_IP in "${NODE_ARRAY[@]}"; do
  CURRENT_NODE=$((CURRENT_NODE + 1))
  
  echo -e "${BOLD}${BLUE}────────────────────────────────────────────────────────────${NC}"
  echo -e "${BOLD}  Node ${CURRENT_NODE}/${NODE_COUNT}: ${NODE_IP}${NC}"
  echo -e "${BOLD}${BLUE}────────────────────────────────────────────────────────────${NC}"

  log_progress "Connecting to ${NODE_IP}..."

  # Run a remote bash script over SSH.
  # We pass NEW_API_ENDPOINT as a positional parameter to bash -s.
  # The heredoc is quoted ('REMOTE_SCRIPT') to prevent local variable expansion.
  SSH_OUTPUT=$(mktemp)
  SSH_EXIT_CODE=0
  
  ssh -o BatchMode=yes \
      -o StrictHostKeyChecking=no \
      -o ConnectTimeout=10 \
      -i "${SSH_KEY}" \
      "${SSH_USER}@${NODE_IP}" \
      "bash -s" -- "${NEW_API_ENDPOINT}" > "${SSH_OUTPUT}" 2>&1 <<'REMOTE_SCRIPT' &
#!/usr/bin/env bash
set -euo pipefail

NEW_API_ENDPOINT="$1"

# Status codes for different outcomes
STATUS_SUCCESS=0
STATUS_SKIP=10
STATUS_ERROR=1

log_remote() {
  echo "PROGRESS:$*"
}

log_remote_done() {
  echo "DONE:$*"
}

log_remote_error() {
  echo "ERROR:$*"
}

log_remote_skip() {
  echo "SKIP:$*"
}

log_remote "Starting update process"

# File paths to update on the node
KUBELET_KUBECONFIG="/var/lib/kubelet/kubeconfig"
ETC_KUBECONFIG="/etc/kubernetes/kubeconfig"
API_ENC_DIR="/etc/kubernetes"
API_ENC_PREFIX="api_enc"

#-------------------------------------------
# 1. Determine OLD_API_ENDPOINT from kubelet kubeconfig
#-------------------------------------------
log_remote "Reading current API endpoint"

if [[ ! -f "${KUBELET_KUBECONFIG}" ]]; then
  log_remote_error "${KUBELET_KUBECONFIG} not found on node"
  exit ${STATUS_ERROR}
fi

OLD_API_ENDPOINT="$(awk '/^\s*server:/ {print $2; exit}' "${KUBELET_KUBECONFIG}")"

if [[ -z "${OLD_API_ENDPOINT}" ]]; then
  log_remote_error "Could not determine old API endpoint"
  exit ${STATUS_ERROR}
fi

log_remote_done "Old endpoint: ${OLD_API_ENDPOINT}"

# Check if update is needed
if [[ "${OLD_API_ENDPOINT}" == "${NEW_API_ENDPOINT}" ]]; then
  log_remote_skip "Endpoints identical - no change needed"
  exit ${STATUS_SKIP}
fi

#-------------------------------------------
# 2. Prepare timestamp for backups
#-------------------------------------------
TS="$(date +%Y%m%d%H%M%S)"
BACKUP_COUNT=0

backup_file() {
  local f="$1"
  if [[ -f "${f}" ]]; then
    sudo cp "${f}" "${f}.bak.${TS}"
    BACKUP_COUNT=$((BACKUP_COUNT + 1))
  fi
}

#-------------------------------------------
# 3. Backup relevant files
#-------------------------------------------
log_remote "Creating backups"

backup_file "${ETC_KUBECONFIG}"
backup_file "${KUBELET_KUBECONFIG}"

# Find and backup api_enc* files (use find for robustness)
while IFS= read -r -d '' f; do
  backup_file "${f}"
done < <(find "${API_ENC_DIR}" -maxdepth 1 -name "${API_ENC_PREFIX}*" -type f -print0 2>/dev/null || true)

log_remote_done "Created ${BACKUP_COUNT} backup(s)"

#-------------------------------------------
# 4. Escape endpoints for sed (handle regex special chars)
#-------------------------------------------
escape_sed() {
  # Escape characters that have special meaning in sed regex:
  # \ & / . * [ ] ^ $
  printf '%s\n' "$1" | sed -e 's/[]\/$*.^[]/\\&/g'
}

ESC_OLD="$(escape_sed "${OLD_API_ENDPOINT}")"
ESC_NEW="$(escape_sed "${NEW_API_ENDPOINT}")"

UPDATE_COUNT=0

replace_in_file() {
  local f="$1"
  if [[ -f "${f}" ]]; then
    sudo sed -i "s|${ESC_OLD}|${ESC_NEW}|g" "${f}"
    UPDATE_COUNT=$((UPDATE_COUNT + 1))
  fi
}

#-------------------------------------------
# 5. Perform replacements
#-------------------------------------------
log_remote "Updating configuration files"

replace_in_file "${ETC_KUBECONFIG}"
replace_in_file "${KUBELET_KUBECONFIG}"

# Update api_enc* files
while IFS= read -r -d '' f; do
  replace_in_file "${f}"
done < <(find "${API_ENC_DIR}" -maxdepth 1 -name "${API_ENC_PREFIX}*" -type f -print0 2>/dev/null || true)

log_remote_done "Updated ${UPDATE_COUNT} file(s)"

#-------------------------------------------
# 6. Restart kubelet
#-------------------------------------------
log_remote "Restarting kubelet service"

if sudo systemctl restart kubelet; then
  log_remote_done "kubelet restarted successfully"
else
  log_remote_error "Failed to restart kubelet"
  exit ${STATUS_ERROR}
fi

log_remote_done "Node update completed"
exit ${STATUS_SUCCESS}
REMOTE_SCRIPT
  
  SSH_PID=$!
  
  # Monitor SSH progress with spinner
  while kill -0 "$SSH_PID" 2>/dev/null; do
    # Read latest progress from output file
    if [[ -f "${SSH_OUTPUT}" ]]; then
      LAST_PROGRESS=$(grep "^PROGRESS:" "${SSH_OUTPUT}" 2>/dev/null | tail -1 | sed 's/^PROGRESS://' || true)
      if [[ -n "${LAST_PROGRESS}" ]]; then
        log_progress "${NODE_IP}: ${LAST_PROGRESS}"
      fi
    fi
    sleep 0.3
  done
  
  wait "$SSH_PID" || SSH_EXIT_CODE=$?
  
  # Process final output
  if [[ -f "${SSH_OUTPUT}" ]]; then
    # Show done messages
    while IFS= read -r line; do
      MSG=$(echo "$line" | sed 's/^DONE://')
      log_done "${NODE_IP}: ${MSG}"
    done < <(grep "^DONE:" "${SSH_OUTPUT}" 2>/dev/null || true)
    
    # Show skip messages
    while IFS= read -r line; do
      MSG=$(echo "$line" | sed 's/^SKIP://')
      log_skip "${NODE_IP}: ${MSG}"
    done < <(grep "^SKIP:" "${SSH_OUTPUT}" 2>/dev/null || true)
    
    # Show error messages
    while IFS= read -r line; do
      MSG=$(echo "$line" | sed 's/^ERROR://')
      log_fail "${NODE_IP}: ${MSG}"
    done < <(grep "^ERROR:" "${SSH_OUTPUT}" 2>/dev/null || true)
    
    rm -f "${SSH_OUTPUT}"
  fi
  
  # Update counters based on exit code
  case ${SSH_EXIT_CODE} in
    0)
      echo -e "  ${GREEN}✓${NC} Node ${NODE_IP} updated successfully"
      SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
      ;;
    10)
      echo -e "  ${YELLOW}○${NC} Node ${NODE_IP} skipped (already up to date)"
      SKIP_COUNT=$((SKIP_COUNT + 1))
      ;;
    *)
      echo -e "  ${RED}✗${NC} Node ${NODE_IP} FAILED (exit code: ${SSH_EXIT_CODE})"
      FAIL_COUNT=$((FAIL_COUNT + 1))
      ;;
  esac
  
  echo
done

############################################
# Final summary
############################################
echo -e "${BOLD}${BLUE}"
echo "=============================================="
echo " Summary"
echo "=============================================="
echo -e "${NC}"

# Progress bar for visual summary
DONE_NODES=$((SUCCESS_COUNT + SKIP_COUNT))
if [[ ${NODE_COUNT} -gt 0 ]]; then
  SUCCESS_PCT=$((SUCCESS_COUNT * 100 / NODE_COUNT))
  SKIP_PCT=$((SKIP_COUNT * 100 / NODE_COUNT))
  FAIL_PCT=$((FAIL_COUNT * 100 / NODE_COUNT))
fi

echo -e "  Total nodes:         ${BOLD}${NODE_COUNT}${NC}"
echo -e "  ${GREEN}Successful updates:${NC}  ${SUCCESS_COUNT}"
echo -e "  ${YELLOW}Skipped (no change):${NC} ${SKIP_COUNT}"
echo -e "  ${RED}Failed updates:${NC}      ${FAIL_COUNT}"
echo

# Visual progress bar
BAR_WIDTH=40
if [[ ${NODE_COUNT} -gt 0 ]]; then
  SUCCESS_BARS=$((SUCCESS_COUNT * BAR_WIDTH / NODE_COUNT))
  SKIP_BARS=$((SKIP_COUNT * BAR_WIDTH / NODE_COUNT))
  FAIL_BARS=$((FAIL_COUNT * BAR_WIDTH / NODE_COUNT))
  
  # Ensure at least 1 bar for non-zero counts
  [[ ${SUCCESS_COUNT} -gt 0 && ${SUCCESS_BARS} -eq 0 ]] && SUCCESS_BARS=1
  [[ ${SKIP_COUNT} -gt 0 && ${SKIP_BARS} -eq 0 ]] && SKIP_BARS=1
  [[ ${FAIL_COUNT} -gt 0 && ${FAIL_BARS} -eq 0 ]] && FAIL_BARS=1
  
  echo -n "  ["
  # Success bars (green)
  for ((i=0; i<SUCCESS_BARS; i++)); do echo -ne "${GREEN}█${NC}"; done
  # Skip bars (yellow)
  for ((i=0; i<SKIP_BARS; i++)); do echo -ne "${YELLOW}█${NC}"; done
  # Fail bars (red)
  for ((i=0; i<FAIL_BARS; i++)); do echo -ne "${RED}█${NC}"; done
  # Empty bars
  EMPTY_BARS=$((BAR_WIDTH - SUCCESS_BARS - SKIP_BARS - FAIL_BARS))
  for ((i=0; i<EMPTY_BARS; i++)); do echo -n "░"; done
  echo "]"
fi

echo

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  log_warn "Completed with ${FAIL_COUNT} node(s) failing to update."
  log_warn "Please investigate failed nodes manually."
  echo
  exit 1
else
  log_info "All nodes processed successfully!"
  echo
  exit 0
fi