CREATE TABLE IF NOT EXISTS segments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(50) NOT NULL,
    vlan_id INT NOT NULL,
    epg_name VARCHAR(255) NOT NULL,
    prefix VARCHAR(50) NOT NULL,
    dhcp BOOLEAN DEFAULT FALSE,
    comments TEXT DEFAULT '',
    cluster_name VARCHAR(255),
    status ENUM('active', 'reserved', 'deprecated') DEFAULT 'active',
    allocated_at TIMESTAMP,
    released BOOLEAN DEFAULT FALSE,
    released_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_site (site),
    INDEX idx_cluster (cluster_name),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;