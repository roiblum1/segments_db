import os
import logging
import sys

# NetBox Configuration
# CRITICAL: These MUST be set as environment variables - never hardcode credentials!
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
NETBOX_SSL_VERIFY = os.getenv("NETBOX_SSL_VERIFY", "true").lower() in ("true", "1", "yes")

# Validate required environment variables at startup
if not NETBOX_URL:
    error_msg = (
        "CRITICAL CONFIGURATION ERROR: NETBOX_URL environment variable is not set!\n"
        "Please set NETBOX_URL in your environment or .env file.\n"
        "Example: export NETBOX_URL='https://your-netbox-instance.com'"
    )
    print(f"ERROR: {error_msg}", file=sys.stderr)
    raise ValueError(error_msg)

if not NETBOX_TOKEN:
    error_msg = (
        "CRITICAL CONFIGURATION ERROR: NETBOX_TOKEN environment variable is not set!\n"
        "Please set NETBOX_TOKEN in your environment or .env file.\n"
        "Generate a token in NetBox: User Menu → API Tokens\n"
        "Example: export NETBOX_TOKEN='your-api-token-here'\n"
        "\n"
        "⚠️  SECURITY WARNING: Never hardcode credentials in source code!"
    )
    print(f"ERROR: {error_msg}", file=sys.stderr)
    raise ValueError(error_msg)

# Sites Configuration
SITES = os.getenv("SITES", "site1,site2,site3").split(",")
SITES = [s.strip() for s in SITES if s.strip()]

# Network + Site IP Prefix Configuration
# New format: "Network1:Site1:192,Network1:Site2:193,Network2:Site1:912,Network2:Site2:913"
# This allows different networks to use different IP prefixes for the same site
NETWORK_SITE_PREFIXES_ENV = os.getenv("NETWORK_SITE_PREFIXES", "")

# Legacy format for backward compatibility (deprecated)
# Format: "site1:192,site2:193,site3:194"
SITE_PREFIXES_ENV = os.getenv("SITE_PREFIXES", "")

def parse_network_site_prefixes(network_site_prefixes_str: str) -> dict:
    """Parse network+site prefixes from environment variable

    Format: "Network1:Site1:192,Network1:Site2:193,Network2:Site1:912"
    Returns: {("Network1", "Site1"): "192", ("Network1", "Site2"): "193", ...}
    """
    prefixes = {}
    if not network_site_prefixes_str:
        return prefixes

    for triple in network_site_prefixes_str.split(","):
        parts = triple.strip().split(":")
        if len(parts) == 3:
            network, site, prefix = parts
            prefixes[(network.strip(), site.strip())] = prefix.strip()
        elif len(parts) == 2:
            # Legacy format: site:prefix (assume default network context)
            site, prefix = parts
            prefixes[("default", site.strip())] = prefix.strip()
    return prefixes

def parse_site_prefixes(site_prefixes_str: str) -> dict:
    """Parse site prefixes from environment variable (LEGACY - for backward compatibility)

    Format: "site1:192,site2:193,site3:194"
    Returns: {"site1": "192", "site2": "193", ...}
    """
    prefixes = {}
    if not site_prefixes_str:
        return prefixes

    for pair in site_prefixes_str.split(","):
        if ":" in pair:
            site, prefix = pair.strip().split(":", 1)
            prefixes[site.strip()] = prefix.strip()
    return prefixes

# Parse new format first, fallback to legacy format
NETWORK_SITE_IP_PREFIXES = parse_network_site_prefixes(NETWORK_SITE_PREFIXES_ENV)
SITE_IP_PREFIXES_LEGACY = parse_site_prefixes(SITE_PREFIXES_ENV)

# If using legacy format, convert to new format with default network
if not NETWORK_SITE_IP_PREFIXES and SITE_IP_PREFIXES_LEGACY:
    NETWORK_SITE_IP_PREFIXES = {("default", site): prefix for site, prefix in SITE_IP_PREFIXES_LEGACY.items()}

def validate_site_prefixes():
    """Validate that all configured sites have IP prefixes defined

    For new multi-network format, this checks that configuration is not empty.
    Individual network+site combinations are validated at segment creation time.
    """
    if not NETWORK_SITE_IP_PREFIXES:
        error_msg = (
            f"CRITICAL CONFIGURATION ERROR: No network+site IP prefixes configured!\n"
            f"Configured sites: {SITES}\n"
            f"Please set NETWORK_SITE_PREFIXES environment variable.\n"
            f"New format: NETWORK_SITE_PREFIXES=\"Network1:Site1:192,Network1:Site2:193,Network2:Site1:912\"\n"
            f"Legacy format: SITE_PREFIXES=\"Site1:192,Site2:193,Site3:194\" (uses 'default' network)"
        )

        # Log error and crash the application
        print(f"ERROR: {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)

    # Log what networks and sites are configured
    configured_combinations = list(NETWORK_SITE_IP_PREFIXES.keys())
    networks = set(network for network, site in configured_combinations)
    sites_with_prefixes = set(site for network, site in configured_combinations)

    print(f"INFO: Configured networks: {sorted(networks)}", file=sys.stderr)
    print(f"INFO: Sites with network prefixes: {sorted(sites_with_prefixes)}", file=sys.stderr)
    print(f"INFO: Total network+site combinations: {len(configured_combinations)}", file=sys.stderr)

def get_site_prefix(site: str, vrf: str = None) -> str:
    """Get the IP prefix for a given site and network/VRF

    Args:
        site: Site name (e.g., "Site1")
        vrf: VRF/Network name (e.g., "Network1"). If None, tries "default" network

    Returns:
        IP prefix (e.g., "192") or None if not found
    """
    # Try with specified VRF first
    if vrf:
        prefix = NETWORK_SITE_IP_PREFIXES.get((vrf, site))
        if prefix:
            return prefix

    # Fall back to "default" network (for legacy compatibility)
    prefix = NETWORK_SITE_IP_PREFIXES.get(("default", site))
    if prefix:
        return prefix

    # Return None if not found (validation will catch this)
    return None

def get_all_networks() -> list:
    """Get list of all configured networks/VRFs"""
    networks = set(network for network, site in NETWORK_SITE_IP_PREFIXES.keys())
    return sorted(networks)

# Logging Configuration
def setup_logging():
    """Configure logging for the application with rotation"""
    from logging.handlers import RotatingFileHandler

    # Get log level from environment variable, default to INFO
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Create rotating file handler: 50MB per file, keep 5 backup files
    rotating_handler = RotatingFileHandler(
        'vlan_manager.log',
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,  # Keep 5 backup files (total ~250MB)
        encoding='utf-8'
    )

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] %(funcName)s() - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            rotating_handler
        ]
    )
    return logging.getLogger(__name__)

# Server Configuration
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))