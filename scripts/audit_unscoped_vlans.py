#!/usr/bin/env python3
"""
audit_unscoped_vlans.py — Pre-deployment audit for unscoped VLANs

Operators run this script against production NetBox BEFORE deploying the
VLAN site isolation fix. It identifies VLANs that have no VLAN Group
assignment (i.e. unscoped VLANs) belonging to the Redbull tenant.

These must be manually remediated before deployment — the app will NOT
automatically migrate existing unscoped VLANs.

Usage:
    export NETBOX_URL="https://your-netbox-instance.com"
    export NETBOX_TOKEN="your-api-token"
    python3 scripts/audit_unscoped_vlans.py

Exit codes:
    0 — No unscoped VLANs found. Safe to deploy.
    1 — Unscoped VLANs found. Remediation required before deployment.
    2 — Script error (missing env vars, connection failure, etc.)
"""

import os
import sys

# Tenant slug — matches TENANT_REDBULL_SLUG constant in netbox_constants.py
# Hardcoded here because this is a standalone script (no app imports).
REDBULL_TENANT_SLUG = "redbull"
REDBULL_TENANT_DISPLAY = "RedBull"


def main():
    # --- Read environment variables ---
    netbox_url = os.environ.get("NETBOX_URL", "").rstrip("/")
    netbox_token = os.environ.get("NETBOX_TOKEN", "")

    if not netbox_url or not netbox_token:
        print("ERROR: NETBOX_URL and NETBOX_TOKEN environment variables must be set.", file=sys.stderr)
        print("  export NETBOX_URL='https://your-netbox-instance.com'", file=sys.stderr)
        print("  export NETBOX_TOKEN='your-api-token'", file=sys.stderr)
        sys.exit(2)

    # --- Connect to NetBox ---
    try:
        import pynetbox
    except ImportError:
        print("ERROR: pynetbox is not installed. Run: pip install pynetbox", file=sys.stderr)
        sys.exit(2)

    try:
        nb = pynetbox.api(netbox_url, token=netbox_token)
        # Verify connectivity
        nb.status()
    except Exception as e:
        print(f"ERROR: Failed to connect to NetBox at {netbox_url}: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"Auditing NetBox for unscoped VLANs (tenant: {REDBULL_TENANT_DISPLAY})...")

    # --- Look up Redbull tenant ---
    try:
        tenant = nb.tenancy.tenants.get(slug=REDBULL_TENANT_SLUG)
    except Exception as e:
        print(f"ERROR: Failed to fetch tenant '{REDBULL_TENANT_SLUG}': {e}", file=sys.stderr)
        sys.exit(2)

    if not tenant:
        print(f"ERROR: Tenant with slug '{REDBULL_TENANT_SLUG}' not found in NetBox.", file=sys.stderr)
        print("       Verify the tenant exists and the slug is correct.", file=sys.stderr)
        sys.exit(2)

    # --- Query for unscoped VLANs (no VLAN Group, scoped to Redbull tenant) ---
    try:
        unscoped_vlans = list(nb.ipam.vlans.filter(group__isnull=True, tenant_id=tenant.id))
    except Exception as e:
        print(f"ERROR: Failed to query VLANs from NetBox: {e}", file=sys.stderr)
        sys.exit(2)

    # --- Report results ---
    if not unscoped_vlans:
        print("No unscoped VLANs found. Safe to deploy.")
        sys.exit(0)

    count = len(unscoped_vlans)
    print(f"Found {count} unscoped VLAN(s) requiring manual remediation:")
    print()

    for vlan in unscoped_vlans:
        vid = getattr(vlan, "vid", "?")
        name = getattr(vlan, "name", "?")
        vlan_id = getattr(vlan, "id", "?")
        print(f"  VID={vid}  name={name}  id={vlan_id}")
        print(f"    Remediation: Delete segment with VLAN ID {vid} via VLAN Manager UI/API, then recreate.")
        print()

    print("ACTION REQUIRED: Remediate the above VLANs before deploying the VLAN site isolation fix.")
    print("Exit code: 1")
    sys.exit(1)


if __name__ == "__main__":
    main()
