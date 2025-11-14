-- VLAN Manager MySQL Schema
-- Converted from NetBox storage to MySQL

-- Create database
CREATE DATABASE IF NOT EXISTS vlan_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE vlan_manager;

-- Tenants table (fixed to "Redbull" in the application)
CREATE TABLE IF NOT EXISTS tenants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_slug (slug)
) ENGINE=InnoDB;

-- VRFs table (Virtual Routing and Forwarding - networks)
CREATE TABLE IF NOT EXISTS vrfs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE COMMENT 'Network name (Network1, Network2, Network3)',
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_name (name)
) ENGINE=InnoDB;

-- Site Groups table (organizational grouping)
CREATE TABLE IF NOT EXISTS site_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_slug (slug)
) ENGINE=InnoDB;

-- Roles table (prefix roles - fixed to "Data")
CREATE TABLE IF NOT EXISTS roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    slug VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_name (name)
) ENGINE=InnoDB;

-- VLAN Groups table (grouping VLANs by VRF and site)
CREATE TABLE IF NOT EXISTS vlan_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE COMMENT 'Format: {VRF}-ClickCluster-{Site}',
    slug VARCHAR(200) NOT NULL UNIQUE,
    vrf_id INT,
    site VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vrf_id) REFERENCES vrfs(id) ON DELETE SET NULL,
    INDEX idx_name (name),
    INDEX idx_vrf_site (vrf_id, site)
) ENGINE=InnoDB;

-- VLANs table (VLAN definitions)
CREATE TABLE IF NOT EXISTS vlans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vlan_id SMALLINT NOT NULL COMMENT 'VLAN ID (1-4094)',
    name VARCHAR(200) NOT NULL COMMENT 'EPG name',
    vlan_group_id INT,
    tenant_id INT NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (vlan_group_id) REFERENCES vlan_groups(id) ON DELETE SET NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    UNIQUE KEY unique_vlan_group (vlan_id, vlan_group_id),
    INDEX idx_vlan_id (vlan_id),
    INDEX idx_name (name),
    INDEX idx_tenant (tenant_id),
    INDEX idx_status (status)
) ENGINE=InnoDB;

-- Segments table (main table - IP prefixes/subnets)
CREATE TABLE IF NOT EXISTS segments (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Core fields
    prefix VARCHAR(50) NOT NULL COMMENT 'IP prefix (e.g., 10.0.0.0/24)',
    vrf_id INT NOT NULL COMMENT 'Network/VRF',
    site VARCHAR(100) NOT NULL COMMENT 'Site name',
    site_group_id INT COMMENT 'Site group reference',
    vlan_id INT COMMENT 'Associated VLAN',
    tenant_id INT NOT NULL,
    role_id INT,

    -- Status and allocation
    status VARCHAR(20) DEFAULT 'active' COMMENT 'active=unallocated, reserved=allocated',
    cluster_name TEXT COMMENT 'Allocated cluster(s) - comma-separated for shared',

    -- Custom fields (matching NetBox custom fields)
    dhcp VARCHAR(20) COMMENT 'DHCP option: Enabled/Disabled/Relay',
    allocated_at TIMESTAMP NULL COMMENT 'When allocated',
    released BOOLEAN DEFAULT FALSE COMMENT 'Whether segment was released',
    released_at TIMESTAMP NULL COMMENT 'When released',

    -- NetBox compatibility
    comments TEXT COMMENT 'User description (Gateway, DHCP server, etc.)',
    description TEXT COMMENT 'EPG name (for display)',

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (vrf_id) REFERENCES vrfs(id) ON DELETE RESTRICT,
    FOREIGN KEY (site_group_id) REFERENCES site_groups(id) ON DELETE SET NULL,
    FOREIGN KEY (vlan_id) REFERENCES vlans(id) ON DELETE SET NULL,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL,

    -- Indexes for performance
    UNIQUE KEY unique_prefix_vrf (prefix, vrf_id),
    INDEX idx_vrf_site (vrf_id, site),
    INDEX idx_status (status),
    INDEX idx_cluster (cluster_name(100)),
    INDEX idx_vlan (vlan_id),
    INDEX idx_site (site),
    INDEX idx_released (released),
    INDEX idx_allocated_at (allocated_at),
    INDEX idx_tenant (tenant_id),

    -- Composite indexes for common queries
    INDEX idx_allocation_query (vrf_id, site, status, released),
    INDEX idx_cluster_search (cluster_name(100), status)
) ENGINE=InnoDB;

-- Insert default data
INSERT IGNORE INTO tenants (name, slug) VALUES ('Redbull', 'redbull');
INSERT IGNORE INTO roles (name, slug) VALUES ('Data', 'data');

-- Insert default VRFs (networks)
INSERT IGNORE INTO vrfs (name, description) VALUES
    ('Network1', 'Network 1'),
    ('Network2', 'Network 2'),
    ('Network3', 'Network 3');

-- Create view for easier querying (optional)
CREATE OR REPLACE VIEW v_segments_detail AS
SELECT
    s.id,
    s.prefix,
    s.site,
    v.name as vrf,
    vlan.vlan_id,
    vlan.name as epg_name,
    s.status,
    s.cluster_name,
    s.dhcp,
    s.comments as description,
    s.allocated_at,
    s.released,
    s.released_at,
    t.name as tenant,
    r.name as role,
    sg.name as site_group,
    s.created_at,
    s.updated_at
FROM segments s
LEFT JOIN vrfs v ON s.vrf_id = v.id
LEFT JOIN vlans vlan ON s.vlan_id = vlan.id
LEFT JOIN tenants t ON s.tenant_id = t.id
LEFT JOIN roles r ON s.role_id = r.id
LEFT JOIN site_groups sg ON s.site_group_id = sg.id;
