"""
Migrate historic schema fixtures to use realistic content.

Strategy:
1. Generate realistic content tree with current ChannelBuilder
2. For each historic schema version, infer schema from existing fixture
3. Transform new content to match old schema structure
4. Export to historic fixture file

This ensures all fixtures represent the same content tree, just with
fields appropriate to each schema version.

Usage:
    python kolibri/core/content/test/migrate_historic_fixtures.py
"""

import json
import os
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kolibri.deployment.default.settings.base')
import django
django.setup()

from kolibri.core.content.test.fixture_presets import create_basic_content_fixture


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '../fixtures')
CONTENT_SCHEMA_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '../contentschema/fixtures')


def infer_schema_from_fixture(fixture_data):
    """
    Analyze a fixture file to understand what the schema looked like.

    Returns dict mapping table names to field information.
    """
    schema = {}

    if isinstance(fixture_data, dict):
        # Schema export format: {table_name: [records]}
        for table_name, records in fixture_data.items():
            if not records or not isinstance(records, list):
                continue

            # Get all field names from all records
            all_fields = set()
            for record in records:
                if isinstance(record, dict):
                    all_fields.update(record.keys())

            schema[table_name] = {
                'fields': sorted(all_fields),
                'sample': records[0] if records else None,
            }

    elif isinstance(fixture_data, list):
        # Django fixture format: [{model, pk, fields}]
        table_fields = {}
        for item in fixture_data:
            model = item.get('model', '')
            if 'fields' not in item:
                continue

            table_name = model
            if table_name not in table_fields:
                table_fields[table_name] = set()

            table_fields[table_name].update(item['fields'].keys())

        # Convert to schema format
        for table_name, fields in table_fields.items():
            schema[table_name] = {
                'fields': sorted(fields),
                'sample': None,
            }

    return schema


def get_default_for_field(field_name):
    """Get appropriate default value for a field that existed in old schema"""
    # MPTT fields
    if field_name in ('lft', 'rght', 'tree_id', 'level', 'sort_order'):
        return None
    # Boolean fields
    if field_name in ('available', 'thumbnail', 'supplementary', 'coach_content',
                      'randomize', 'is_manipulable'):
        return False
    # Numeric fields
    if 'size' in field_name or field_name in ('priority', 'number_of_assessments'):
        return None
    # List/array fields
    if field_name in ('assessment_item_ids',):
        return "[]"
    # Dict/JSON fields
    if field_name in ('mastery_model', 'options'):
        return "{}"
    # String fields
    return ""


def transform_record_to_schema(record, allowed_fields):
    """
    Transform a record to match a historic schema.

    Args:
        record: Dict of field values from new content
        allowed_fields: List of fields that existed in historic schema

    Returns:
        Transformed record with only allowed fields
    """
    transformed = {}

    for field in allowed_fields:
        if field in record:
            transformed[field] = record[field]
        else:
            # Field exists in old schema but not in our new data
            # Use appropriate default based on field name
            transformed[field] = get_default_for_field(field)

    return transformed


def map_table_names(new_tables, old_tables):
    """
    Map new table names to old table names.

    Returns dict: {old_table: new_table}
    """
    mapping = {}

    # Try exact match first
    for old_table in old_tables:
        if old_table in new_tables:
            mapping[old_table] = old_table
        else:
            # Try to find similar name (handle prefix differences)
            # e.g., content_contentnode vs contentnode
            old_suffix = old_table.split('_')[-1]
            for new_table in new_tables:
                new_suffix = new_table.split('_')[-1]
                if old_suffix == new_suffix:
                    mapping[old_table] = new_table
                    break

    return mapping


def transform_to_schema(new_data, old_schema):
    """
    Transform new realistic content data to match old schema structure.

    Args:
        new_data: Dict from ChannelBuilder.data (current schema)
        old_schema: Schema inferred from historic fixture

    Returns:
        Data structure matching old schema with new realistic content
    """
    transformed = {}

    # Map new table names to old table names
    table_mapping = map_table_names(new_data.keys(), old_schema.keys())

    for old_table, new_table in table_mapping.items():
        if new_table not in new_data:
            continue

        old_fields = old_schema[old_table]['fields']
        new_records = new_data[new_table]

        transformed[old_table] = [
            transform_record_to_schema(record, old_fields)
            for record in new_records
        ]

    # Handle tables that existed in old schema but not in new data
    for old_table in old_schema:
        if old_table not in transformed:
            # This table existed in old schema but we don't have data
            transformed[old_table] = []

    return transformed


def convert_to_django_fixture_format(data_dict):
    """Convert {table: [records]} format to Django fixture format"""
    fixture = []

    for table_name, records in data_dict.items():
        for record in records:
            pk = record.get('id')
            fields = {k: v for k, v in record.items() if k != 'id'}

            fixture.append({
                'model': table_name,
                'pk': pk,
                'fields': fields,
            })

    return fixture


def migrate_historic_fixture(fixture_filename, new_content_builder, base_dir=FIXTURES_DIR):
    """
    Migrate a single historic fixture to use realistic content.

    Args:
        fixture_filename: Name of the historic fixture file
        new_content_builder: ChannelBuilder instance with realistic data
        base_dir: Directory containing the fixture file
    """
    filepath = os.path.join(base_dir, fixture_filename)

    if not os.path.exists(filepath):
        print(f"Skipping {fixture_filename} (not found)")
        return False

    print(f"Migrating {fixture_filename}...")

    # Load old fixture
    with open(filepath, 'r') as f:
        old_data = json.load(f)

    # Infer schema from old fixture
    old_schema = infer_schema_from_fixture(old_data)
    print(f"  Inferred schema: {len(old_schema)} tables")

    # Get new realistic content data
    new_data = new_content_builder.data

    # Transform new data to match old schema
    migrated_data = transform_to_schema(new_data, old_schema)

    # Preserve the same format (dict vs list)
    if isinstance(old_data, dict):
        output = migrated_data
    else:
        # Convert back to Django fixture format
        output = convert_to_django_fixture_format(migrated_data)

    # Write migrated fixture
    with open(filepath, 'w') as f:
        # Use compact JSON (no indentation) to match existing format
        json.dump(output, f)

    print(f"✓ Migrated {fixture_filename}")
    return True


def migrate_all_historic_fixtures():
    """Main migration function"""

    print("=" * 70)
    print("Migrating Historic Content Fixtures")
    print("=" * 70)
    print()
    print("Generating new realistic content with ChannelBuilder...")

    # Generate realistic content
    builder = create_basic_content_fixture()

    print(f"Generated content tree:")
    print(f"  - Channel: {builder.channel['name']}")
    print(f"  - Nodes: {len(builder.nodes)}")
    print(f"  - Files: {len(builder.files)}")
    print(f"  - Local files: {len(builder.localfiles)}")
    print()

    print("Migrating historic schema fixtures...")
    print()

    # Migrate schema version fixtures
    schema_fixtures = [
        '1_content_data.json',
        '2_content_data.json',
        '3_content_data.json',
        '4_content_data.json',
        '5_content_data.json',
        'unversioned_content_data.json',
        'v0.2.0-beta1_content_data.json',
        'v0.4.0-beta3_content_data.json',
    ]

    migrated_count = 0
    for fixture in schema_fixtures:
        if migrate_historic_fixture(fixture, builder):
            migrated_count += 1

    # Migrate test fixtures
    print()
    print("Migrating test fixtures...")
    print()

    test_fixtures = [
        'content_test.json',
        'channel_test.json',
    ]

    for fixture in test_fixtures:
        if migrate_historic_fixture(fixture, builder):
            migrated_count += 1

    # Migrate source fixture (in different directory)
    print()
    print("Migrating source fixture...")
    print()

    if migrate_historic_fixture('content_import_test.json', builder, CONTENT_SCHEMA_FIXTURES_DIR):
        migrated_count += 1

    print()
    print("=" * 70)
    print(f"✓ Migration complete! {migrated_count} fixtures migrated.")
    print("=" * 70)
    print()
    print("All fixtures now represent the same realistic content tree,")
    print("with fields appropriate to each schema version.")
    print()
    print("NEXT STEPS:")
    print("1. Review the changes with: git diff kolibri/core/content/fixtures/")
    print("2. Test the fixtures: pytest kolibri/core/content/test/")
    print("3. Commit if tests pass")


if __name__ == '__main__':
    try:
        migrate_all_historic_fixtures()
    except Exception as e:
        print(f"\n✗ Error during migration: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
