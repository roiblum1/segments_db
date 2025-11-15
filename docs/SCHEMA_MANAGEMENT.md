# Schema Management Guide

## Problem: Adding New Fields Was Hard

Previously, adding a new field to segments required changes in multiple places:
1. Database schema SQL file
2. Pydantic model definition
3. Storage layer field mapping
4. Possibly validators
5. UI/Frontend code

This led to errors, inconsistencies, and maintenance headaches!

## Solution: Single Source of Truth

We now use a **centralized schema definition** approach:

```
src/models/segment_schema.py   ← SINGLE SOURCE OF TRUTH
         ↓
scripts/generate_schema.py     ← Auto-generates everything
         ↓
    generated/
    ├── segments_table.sql      ← SQL CREATE TABLE
    ├── segment_model.py        ← Pydantic model
    ├── field_mapping.py        ← Field mappings
    └── FIELDS.md               ← Documentation
```

## How to Add a New Field

### Step 1: Edit the Schema Definition

Open `src/models/segment_schema.py` and add your field to `SEGMENT_FIELDS`:

```python
SEGMENT_FIELDS = [
    # ... existing fields ...

    # YOUR NEW FIELD
    SegmentField(
        name="priority",              # Python field name
        python_type=int,              # Python type
        sql_type="INT",               # SQL type
        db_column="priority_level",   # Database column (optional, defaults to name)
        required=False,               # Is it required?
        default=0,                    # Default value
        editable=True,                # Can users edit it?
        in_api=True,                  # Include in API responses?
        description="Segment priority level (0-10)",
        validator="validate_priority" # Validation function name (optional)
    ),
]
```

### Step 2: Run the Generator

```bash
python3 scripts/generate_schema.py
```

This generates:
- SQL CREATE TABLE statement
- Pydantic model
- Field mapping for storage layer
- Documentation

### Step 3: Review and Apply Changes

Check the `generated/` directory:

```bash
# Review what was generated
cat generated/segment_model.py
cat generated/segments_table.sql
cat generated/field_mapping.py
cat generated/FIELDS.md
```

### Step 4: Update Your Code

1. **Database**: Use the generated SQL to update your schema
   ```bash
   # For Docker
   podman-compose down
   podman volume rm segments_2_mysql_data  # Careful! Deletes data
   podman-compose up -d

   # For local MySQL
   mysql -u root -p < generated/segments_table.sql
   ```

2. **Pydantic Model**: Copy the generated model to `src/models/schemas.py`

3. **Storage Layer**: Update field mapping in `src/database/mysql_storage.py`

4. **Validators** (if needed): Add validation function to `src/utils/validators.py`
   ```python
   @staticmethod
   def validate_priority(priority: int):
       if not 0 <= priority <= 10:
           raise ValueError("Priority must be between 0 and 10")
   ```

### Step 5: Update the UI (Manual)

Update the frontend to display/edit the new field:

1. **HTML**: Add table column in `static/html/index.html`
2. **JavaScript**: Update form and table rendering in `static/js/app.js`

### Step 6: Test

```bash
# Run tests
pytest tests/ -v

# Test manually via API
curl -X POST http://localhost:9000/api/segments \
  -H "Content-Type: application/json" \
  -d '{
    "site": "Site1",
    "vlan_id": 500,
    "epg_name": "TEST",
    "segment": "192.1.50.0/24",
    "dhcp": true,
    "priority": 5,
    "description": "Test with new field"
  }'
```

## Field Configuration Options

### SegmentField Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `name` | str | Python field name | `"priority"` |
| `python_type` | type | Python type annotation | `int`, `str`, `bool` |
| `sql_type` | str | MySQL column type | `"INT"`, `"VARCHAR(255)"` |
| `db_column` | str | Database column name (if different) | `"priority_level"` |
| `required` | bool | Is field required? | `True`, `False` |
| `default` | Any | Default value | `0`, `""`, `None` |
| `editable` | bool | Can users edit this field? | `True`, `False` |
| `in_api` | bool | Include in API responses? | `True`, `False` |
| `description` | str | Field description | `"Priority level"` |
| `validator` | str | Validation function name | `"validate_priority"` |

### Field Type Examples

```python
# String field
SegmentField(
    name="zone",
    python_type=str,
    sql_type="VARCHAR(50)",
    required=False,
    default="default"
)

# Integer field with range
SegmentField(
    name="priority",
    python_type=int,
    sql_type="INT",
    default=0,
    validator="validate_priority"
)

# Boolean flag
SegmentField(
    name="auto_assign",
    python_type=bool,
    sql_type="BOOLEAN",
    default=True
)

# Optional timestamp
SegmentField(
    name="expires_at",
    python_type=Optional[str],
    sql_type="TIMESTAMP",
    required=False,
    default=None
)

# Enum field
SegmentField(
    name="environment",
    python_type=str,
    sql_type="ENUM('dev', 'staging', 'prod')",
    default="dev"
)
```

## Benefits

✅ **Single Source of Truth**: All field definitions in one place
✅ **Auto-Generation**: SQL, models, and mappings generated automatically
✅ **Consistency**: No more mismatched types between layers
✅ **Documentation**: Field docs auto-generated
✅ **Less Error-Prone**: Change once, regenerate everywhere
✅ **Type Safety**: Clear type definitions for all fields
✅ **Easy Refactoring**: Rename a field in one place

## Migration Guide

### Example: Adding "Environment" Field

**Before** (modify 5+ files manually):
- ❌ Update `mysql_schema.sql`
- ❌ Update `Segment` Pydantic model
- ❌ Update field mapping in storage
- ❌ Update validators
- ❌ Update documentation

**After** (modify 1 file, run generator):
1. ✅ Add field to `SEGMENT_FIELDS`
2. ✅ Run `python3 scripts/generate_schema.py`
3. ✅ Copy generated code
4. ✅ Test!

## Advanced: Custom Code Generation

You can extend `scripts/generate_schema.py` to generate:
- TypeScript interfaces for frontend
- GraphQL schema
- API documentation
- Database migration scripts
- Test fixtures

## Best Practices

1. **Always use the generator** - Don't manually edit generated files
2. **Keep validators separate** - Don't put complex logic in schema
3. **Document your fields** - Use clear, descriptive descriptions
4. **Test after changes** - Run full test suite
5. **Version control** - Commit schema changes with generated code

## Troubleshooting

### Generator Fails
```bash
# Check Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Run with verbose output
python3 -v scripts/generate_schema.py
```

### Type Mismatches
Ensure `python_type` matches `sql_type`:
- `int` → `INT`, `BIGINT`
- `str` → `VARCHAR(n)`, `TEXT`
- `bool` → `BOOLEAN`, `TINYINT(1)`
- `Optional[T]` → Add `required=False`

### Database Column Name Conflicts
Use `db_column` parameter:
```python
SegmentField(
    name="segment",      # Python name
    db_column="prefix",  # Database name
    ...
)
```

## See Also

- [README.md](../README.md) - Main documentation
- [API Documentation](../README.md#api-documentation) - API endpoints
- [Database Schema](../README.md#database-schema) - Current schema
