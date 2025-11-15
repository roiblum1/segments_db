#!/usr/bin/env python3
"""
Schema Code Generator
Generates Pydantic models, SQL, and documentation from segment_schema.py
Run this after modifying SEGMENT_FIELDS to regenerate all dependent code
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models.segment_schema import (
    SEGMENT_FIELDS,
    get_user_editable_fields,
    get_field_mapping,
    generate_sql_create_table,
    generate_field_documentation,
    get_pydantic_field_definition
)


def generate_pydantic_model() -> str:
    """Generate Pydantic model code"""
    lines = [
        '"""',
        'Auto-generated Pydantic models from segment_schema.py',
        'DO NOT EDIT DIRECTLY - Run scripts/generate_schema.py to regenerate',
        '"""',
        'from pydantic import BaseModel, Field',
        'from typing import Optional',
        '',
        '',
        'class Segment(BaseModel):',
        '    """Segment model for API requests"""',
    ]

    # Add fields
    for field in get_user_editable_fields():
        type_ann, field_def = get_pydantic_field_definition(field)
        type_str = str(type_ann).replace("typing.", "").replace("<class '", "").replace("'>", "")

        if field_def:
            lines.append(f'    {field.name}: {type_str} = {field_def}')
        else:
            lines.append(f'    {field.name}: {type_str}')

    lines.append('')
    lines.append('    class Config:')
    lines.append('        json_schema_extra = {')
    lines.append('            "example": {')
    lines.append('                "site": "Site1",')
    lines.append('                "vlan_id": 100,')
    lines.append('                "epg_name": "EPG_PROD_01",')
    lines.append('                "segment": "192.1.1.0/24",')
    lines.append('                "dhcp": True,')
    lines.append('                "description": "Production network"')
    lines.append('            }')
    lines.append('        }')

    return '\n'.join(lines)


def generate_storage_mapping() -> str:
    """Generate field mapping code for storage layer"""
    lines = [
        '# Auto-generated field mapping',
        '# Python field name -> Database column name',
        'FIELD_MAPPING = {',
    ]

    for py_name, db_name in get_field_mapping().items():
        lines.append(f'    "{py_name}": "{db_name}",')

    lines.append('}')
    return '\n'.join(lines)


def main():
    """Generate all schema-derived code"""
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'generated')
    os.makedirs(output_dir, exist_ok=True)

    print("🔧 Generating code from segment_schema.py...\n")

    # 1. Generate SQL
    print("1. Generating SQL CREATE TABLE statement...")
    sql = generate_sql_create_table()
    sql_file = os.path.join(output_dir, 'segments_table.sql')
    with open(sql_file, 'w') as f:
        f.write(sql)
    print(f"   ✓ Written to: {sql_file}")

    # 2. Generate Pydantic model
    print("2. Generating Pydantic model...")
    pydantic_code = generate_pydantic_model()
    pydantic_file = os.path.join(output_dir, 'segment_model.py')
    with open(pydantic_file, 'w') as f:
        f.write(pydantic_code)
    print(f"   ✓ Written to: {pydantic_file}")

    # 3. Generate field mapping
    print("3. Generating field mapping...")
    mapping_code = generate_storage_mapping()
    mapping_file = os.path.join(output_dir, 'field_mapping.py')
    with open(mapping_file, 'w') as f:
        f.write(mapping_code)
    print(f"   ✓ Written to: {mapping_file}")

    # 4. Generate documentation
    print("4. Generating documentation...")
    docs = generate_field_documentation()
    docs_file = os.path.join(output_dir, 'FIELDS.md')
    with open(docs_file, 'w') as f:
        f.write(docs)
    print(f"   ✓ Written to: {docs_file}")

    print("\n✅ Code generation complete!")
    print("\nNext steps:")
    print("1. Review generated files in generated/")
    print("2. Copy/merge changes to actual source files")
    print("3. Test the changes")
    print("\nGenerated files:")
    print(f"  - {sql_file}")
    print(f"  - {pydantic_file}")
    print(f"  - {mapping_file}")
    print(f"  - {docs_file}")


if __name__ == "__main__":
    main()
