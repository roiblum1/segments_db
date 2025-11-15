# Segment Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| site | str | Yes | Site name (e.g., Site1, Site2, Site3) |
| vlan_id | int | Yes | VLAN ID (1-4094) |
| epg_name | str | Yes | EPG/VLAN name |
| segment | str | Yes | Network segment (e.g., 192.1.1.0/24) |
| dhcp | bool | Yes | DHCP enabled |
| description | str | No | Segment description/comments |
| cluster_name | Optional[str] | No | Allocated cluster name |
| status | str | Yes | Segment status |
| allocated_at | Optional[str] | No | When segment was allocated |
| released | bool | Yes | Whether segment was released |
| released_at | Optional[str] | No | When segment was released |
| created_at | str | Yes | When segment was created |
| updated_at | str | Yes | When segment was last updated |