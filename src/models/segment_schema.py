"""
Centralized Segment Schema Definition
Single source of truth for segment fields - modify here to add/remove fields
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class SegmentField:
    """Definition of a segment field"""
    name: str
    python_type: type
    sql_type: str
    required: bool = True
    default: Any = None
    description: str = ""
    # Mapping to different column names in database
    db_column: Optional[str] = None
    # Whether this field is user-editable
    editable: bool = True
    # Whether this field should appear in API responses
    in_api: bool = True
    # Validation function name (optional)
    validator: Optional[str] = None

    @property
    def db_field_name(self) -> str:
        """Get the database column name"""
        return self.db_column or self.name


# =============================================================================
# SEGMENT SCHEMA - SINGLE SOURCE OF TRUTH
# Modify this to add/remove fields from segments
# =============================================================================

SEGMENT_FIELDS = [
    # Core identification fields
    SegmentField(
        name="site",
        python_type=str,
        sql_type="VARCHAR(50)",
        description="Site name (e.g., Site1, Site2, Site3)",
        validator="validate_site"
    ),
    SegmentField(
        name="vlan_id",
        python_type=int,
        sql_type="INT",
        description="VLAN ID (1-4094)",
        validator="validate_vlan_id"
    ),
    SegmentField(
        name="epg_name",
        python_type=str,
        sql_type="VARCHAR(255)",
        description="EPG/VLAN name",
        validator="validate_epg_name"
    ),

    # Network segment
    SegmentField(
        name="segment",
        python_type=str,
        sql_type="VARCHAR(50)",
        db_column="prefix",  # Different name in database
        description="Network segment (e.g., 192.1.1.0/24)",
        validator="validate_segment_format"
    ),

    # Configuration fields
    SegmentField(
        name="dhcp",
        python_type=bool,
        sql_type="BOOLEAN",
        default=False,
        description="DHCP enabled"
    ),
    SegmentField(
        name="description",
        python_type=str,
        sql_type="TEXT",
        db_column="comments",  # Different name in database
        required=False,
        default="",
        description="Segment description/comments",
        validator="validate_description"
    ),

    # Allocation fields (system-managed)
    SegmentField(
        name="cluster_name",
        python_type=Optional[str],
        sql_type="VARCHAR(255)",
        required=False,
        default=None,
        editable=False,  # System manages this
        description="Allocated cluster name"
    ),
    SegmentField(
        name="status",
        python_type=str,
        sql_type="ENUM('active', 'reserved', 'deprecated')",
        default="active",
        editable=False,
        description="Segment status"
    ),

    # Metadata fields (system-managed)
    SegmentField(
        name="allocated_at",
        python_type=Optional[str],
        sql_type="TIMESTAMP",
        required=False,
        default=None,
        editable=False,
        in_api=True,
        description="When segment was allocated"
    ),
    SegmentField(
        name="released",
        python_type=bool,
        sql_type="BOOLEAN",
        default=False,
        editable=False,
        description="Whether segment was released"
    ),
    SegmentField(
        name="released_at",
        python_type=Optional[str],
        sql_type="TIMESTAMP",
        required=False,
        default=None,
        editable=False,
        description="When segment was released"
    ),
    SegmentField(
        name="created_at",
        python_type=str,
        sql_type="TIMESTAMP",
        default="CURRENT_TIMESTAMP",
        editable=False,
        description="When segment was created"
    ),
    SegmentField(
        name="updated_at",
        python_type=str,
        sql_type="TIMESTAMP",
        default="CURRENT_TIMESTAMP",
        editable=False,
        description="When segment was last updated"
    ),
]


# =============================================================================
# Helper Functions
# =============================================================================

def get_user_editable_fields() -> list[SegmentField]:
    """Get only user-editable fields"""
    return [f for f in SEGMENT_FIELDS if f.editable]


def get_required_fields() -> list[SegmentField]:
    """Get required fields"""
    return [f for f in SEGMENT_FIELDS if f.required]


def get_api_fields() -> list[SegmentField]:
    """Get fields that should appear in API responses"""
    return [f for f in SEGMENT_FIELDS if f.in_api]


def get_field_mapping() -> Dict[str, str]:
    """Get mapping from Python field names to database column names"""
    return {f.name: f.db_field_name for f in SEGMENT_FIELDS}


def get_reverse_field_mapping() -> Dict[str, str]:
    """Get mapping from database column names to Python field names"""
    return {f.db_field_name: f.name for f in SEGMENT_FIELDS}


def get_pydantic_field_definition(field: SegmentField) -> tuple:
    """
    Generate Pydantic field definition
    Returns: (type_annotation, field_definition)
    """
    from pydantic import Field

    # Build type annotation
    type_ann = field.python_type
    if not field.required and field.default is None:
        from typing import Optional
        if not str(type_ann).startswith('typing.Optional'):
            type_ann = Optional[field.python_type]

    # Build field definition
    field_kwargs = {"description": field.description}
    if field.default is not None and field.default != "CURRENT_TIMESTAMP":
        field_kwargs["default"] = field.default
    elif not field.required:
        field_kwargs["default"] = None

    return type_ann, Field(**field_kwargs)


def generate_sql_create_table() -> str:
    """Generate SQL CREATE TABLE statement from schema"""
    lines = ["CREATE TABLE IF NOT EXISTS segments ("]
    lines.append("    id INT AUTO_INCREMENT PRIMARY KEY,")

    for field in SEGMENT_FIELDS:
        col_def = f"    {field.db_field_name} {field.sql_type}"

        # Add constraints
        if field.required and field.default is None:
            col_def += " NOT NULL"

        if field.default is not None and field.default != "CURRENT_TIMESTAMP":
            if isinstance(field.default, str):
                col_def += f" DEFAULT '{field.default}'"
            elif isinstance(field.default, bool):
                col_def += f" DEFAULT {str(field.default).upper()}"
            else:
                col_def += f" DEFAULT {field.default}"
        elif field.default == "CURRENT_TIMESTAMP":
            col_def += " DEFAULT CURRENT_TIMESTAMP"

        if field.name == "updated_at":
            col_def += " ON UPDATE CURRENT_TIMESTAMP"

        col_def += ","
        lines.append(col_def)

    # Add indexes
    lines.append("    INDEX idx_site (site),")
    lines.append("    INDEX idx_cluster (cluster_name),")
    lines.append("    INDEX idx_status (status)")

    lines.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;")

    return "\n".join(lines)


# =============================================================================
# Auto-generated documentation
# =============================================================================

def generate_field_documentation() -> str:
    """Generate markdown documentation for fields"""
    lines = ["# Segment Fields\n"]
    lines.append("| Field | Type | Required | Description |")
    lines.append("|-------|------|----------|-------------|")

    for field in SEGMENT_FIELDS:
        required = "Yes" if field.required else "No"
        py_type = str(field.python_type).replace("typing.", "").replace("<class '", "").replace("'>", "")
        lines.append(f"| {field.name} | {py_type} | {required} | {field.description} |")

    return "\n".join(lines)


if __name__ == "__main__":
    # Print generated SQL for verification
    print("=== Generated SQL ===")
    print(generate_sql_create_table())
    print("\n=== Field Documentation ===")
    print(generate_field_documentation())
    print("\n=== Field Mappings ===")
    print("Python -> Database:", get_field_mapping())
