# Scripts Directory - Usage Guide

This document describes the utility scripts available in the `scripts/` directory and how to use them.

## Overview

The `scripts/` directory contains administrative and code generation utilities for the VLAN Manager application:

- **init_database.py** - Initialize MySQL database manually
- **generate_schema.py** - Generate code from schema definition

---

## init_database.py

### Purpose
Initializes the MySQL database by creating the `segments` table with the proper schema. This script is useful for local development or manual database setup outside of Docker.

### When to Use
- Setting up local development environment without Docker
- Manually recreating the database schema
- Troubleshooting database issues
- Testing database migrations

### Prerequisites
- MySQL server running and accessible
- Database credentials configured in `.env` file or environment variables
- Required Python packages installed (`pip install -r requirements.txt`)

### Usage

```bash
# From project root directory
python3 scripts/init_database.py
```

### What It Does
1. Connects to MySQL server using credentials from environment
2. Creates database if it doesn't exist
3. Creates `segments` table with all required fields:
   - id (AUTO_INCREMENT PRIMARY KEY)
   - site, vlan_id, epg_name
   - prefix (network segment)
   - dhcp, comments
   - cluster_name, status
   - allocated_at, released, released_at
   - created_at, updated_at
4. Creates indexes for performance:
   - idx_site (site)
   - idx_cluster (cluster_name)
   - idx_status (status)

### Environment Variables Required
```bash
MYSQL_HOST=localhost          # MySQL server host
MYSQL_PORT=3306              # MySQL server port
MYSQL_DATABASE=vlan_manager  # Database name
MYSQL_USER=root              # MySQL user
MYSQL_PASSWORD=root          # MySQL password
```

### Example Output
```
Database 'vlan_manager' created successfully
Table 'segments' created successfully
✓ Database initialized successfully
```

### Troubleshooting
- **Connection refused**: Ensure MySQL server is running
- **Access denied**: Check MySQL credentials in .env
- **Table already exists**: Script is safe to re-run, but will show warning

---

## generate_schema.py

### Purpose
Auto-generates code from the centralized schema definition in `src/models/segment_schema.py`. This is the core of the schema management system that eliminates the need to manually update multiple files when adding or modifying segment fields.

### When to Use
- **After adding a new field** to `SEGMENT_FIELDS` in `segment_schema.py`
- **After modifying a field** (type, validation, description, etc.)
- **After removing a field** from the schema
- **Before committing schema changes** to ensure all generated code is in sync

### Prerequisites
- Python 3.11+
- `src/models/segment_schema.py` exists and is valid

### Usage

```bash
# From project root directory
python3 scripts/generate_schema.py
```

### What It Generates

The script creates 4 files in the `generated/` directory:

#### 1. segments_table.sql
SQL CREATE TABLE statement with all fields, constraints, defaults, and indexes.

**Location**: `generated/segments_table.sql`

**Used For**: Database migrations and documentation

**Example**:
```sql
CREATE TABLE IF NOT EXISTS segments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(50) NOT NULL,
    vlan_id INT NOT NULL,
    prefix VARCHAR(50) NOT NULL,
    -- ... all fields from schema
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### 2. segment_model.py
Pydantic model definitions for API request validation.

**Location**: `generated/segment_model.py`

**Used For**: API request/response validation (can replace parts of `src/models/schemas.py`)

**Example**:
```python
class Segment(BaseModel):
    site: str = Field(description="Site name (e.g., Site1, Site2, Site3)")
    vlan_id: int = Field(description="VLAN ID (1-4094)")
    # ... all fields with types and validation
```

#### 3. field_mapping.py
Python field names to database column names mapping.

**Location**: `generated/field_mapping.py`

**Used For**: Storage layer (`src/database/mysql_storage.py`)

**Example**:
```python
FIELD_MAPPING = {
    "segment": "prefix",      # segment → prefix in DB
    "description": "comments", # description → comments in DB
    # ... all field mappings
}
```

#### 4. FIELDS.md
Markdown documentation table of all fields.

**Location**: `generated/FIELDS.md`

**Used For**: API documentation and README

**Example**:
```markdown
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| site | str | Yes | Site name (e.g., Site1, Site2, Site3) |
| vlan_id | int | Yes | VLAN ID (1-4094) |
```

### Example Workflow: Adding a New Field

#### Step 1: Edit Schema Definition
Edit `src/models/segment_schema.py` and add your new field:

```python
SEGMENT_FIELDS = [
    # ... existing fields ...
    SegmentField(
        name="priority",
        python_type=int,
        sql_type="INT",
        default=5,
        required=False,
        description="Segment priority level (0-10)",
        validator="validate_priority"
    ),
]
```

#### Step 2: Run Generator
```bash
python3 scripts/generate_schema.py
```

#### Step 3: Verify Output
```bash
✓ Generated: generated/segments_table.sql
✓ Generated: generated/segment_model.py
✓ Generated: generated/field_mapping.py
✓ Generated: generated/FIELDS.md

All schema files generated successfully!
```

#### Step 4: Check Generated Files
```bash
# Check SQL includes new field
grep "priority" generated/segments_table.sql

# Check Pydantic model includes new field
grep "priority" generated/segment_model.py

# Check field mapping
grep "priority" generated/field_mapping.py
```

#### Step 5: Apply Changes
- Update database with new SQL (run migration)
- Update storage layer to use new field mapping
- Implement validator function if specified
- Update UI forms to include new field

### Output Format

The script provides clear output showing what was generated:

```
=== Generating Schema Files ===

✓ Generated: generated/segments_table.sql
✓ Generated: generated/segment_model.py
✓ Generated: generated/field_mapping.py
✓ Generated: generated/FIELDS.md

All schema files generated successfully!

=== Preview: segments_table.sql ===
CREATE TABLE IF NOT EXISTS segments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    site VARCHAR(50) NOT NULL,
    ...
```

### Best Practices

1. **Always regenerate after schema changes**
   ```bash
   # Make this a habit after editing segment_schema.py
   python3 scripts/generate_schema.py
   ```

2. **Commit generated files**
   ```bash
   git add generated/
   git commit -m "Update schema: added priority field"
   ```

3. **Use pre-commit hooks** (optional)
   ```bash
   # .git/hooks/pre-commit
   #!/bin/bash
   python3 scripts/generate_schema.py
   git add generated/
   ```

4. **Review generated files before committing**
   ```bash
   git diff generated/
   ```

### Troubleshooting

**Problem**: Import errors when running generator
**Solution**: Ensure you're in the project root directory with virtual environment activated

**Problem**: Generated files look wrong
**Solution**: Check `segment_schema.py` for syntax errors in `SEGMENT_FIELDS` list

**Problem**: Need to regenerate everything
**Solution**: Delete `generated/` directory and run script again
```bash
rm -rf generated/
python3 scripts/generate_schema.py
```

---

## Integration with Development Workflow

### Typical Development Flow

1. **Identify need for new field**
   - Example: Need to track segment priority

2. **Update schema definition**
   ```bash
   vim src/models/segment_schema.py
   # Add SegmentField for priority
   ```

3. **Generate code**
   ```bash
   python3 scripts/generate_schema.py
   ```

4. **Review generated files**
   ```bash
   git diff generated/
   ```

5. **Update database**
   ```bash
   # Option 1: Recreate from scratch (dev only)
   python3 scripts/init_database.py

   # Option 2: Write migration (production)
   # Create migration SQL from segments_table.sql
   ```

6. **Update application code**
   - Copy field mapping to storage layer
   - Implement validator function
   - Update UI forms

7. **Test changes**
   ```bash
   pytest tests/
   ```

8. **Commit everything**
   ```bash
   git add src/models/segment_schema.py generated/
   git commit -m "feat: Add priority field to segments"
   ```

---

## Additional Resources

- **Schema Management Guide**: [docs/SCHEMA_MANAGEMENT.md](SCHEMA_MANAGEMENT.md) - Complete guide to schema system
- **Schema Test Results**: [docs/SCHEMA_TEST_RESULTS.md](SCHEMA_TEST_RESULTS.md) - Validation testing results
- **Main README**: [../README.md](../README.md) - Project overview and setup

---

## Summary

The scripts directory provides two essential tools:

| Script | Purpose | When to Use | Output |
|--------|---------|-------------|--------|
| **init_database.py** | Initialize MySQL database | Local setup, troubleshooting | Creates database and tables |
| **generate_schema.py** | Generate code from schema | After any schema changes | 4 files in generated/ directory |

Both scripts are designed to be safe to run multiple times and provide clear output about what they're doing.

**Key Principle**: `segment_schema.py` is the single source of truth. All other code is generated from it.
