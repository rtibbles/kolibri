# Content Test Fixtures

## Overview

Test fixtures have been enhanced to use realistic, meaningful content instead of generic placeholders like "c1", "c2", and "balbla1".

All fixtures now represent the same underlying content tree with:
- Meaningful titles (e.g., "Introduction to Algebra" instead of "c1")
- Detailed descriptions (e.g., "Learn fundamental algebraic concepts..." instead of "balbla2")
- Realistic authors (e.g., "Kolibri Content Team" instead of blank or "eli")
- Appropriate licenses (e.g., "CC BY" instead of "WTFPL")

## Fixture Generation Architecture

### ChannelBuilder Enhancement

The `ChannelBuilder` class in `helpers.py` has been enhanced with:

1. **Dependency Injection**: Accepts a `models` parameter to work with dynamically registered Django models
2. **Realistic Content Generation**: Content libraries organized by subject (math, science) and content kind
3. **Backward Compatibility**: Defaults to standard models if none provided

### Fixture Presets

The `fixture_presets.py` module defines standard content trees:

- `create_basic_content_fixture()`: Standard fixture used across all schema versions
- Each preset function can accept injected models for schema version compatibility

### Content Tree Structure

All fixtures represent this canonical content tree:

```
Learning Resources (root)
├── Introduction to Algebra (video)
│   └── Has prerequisite: root
│   └── Related to: Advanced Mathematics
├── Advanced Mathematics (topic)
│   ├── Linear Equations Practice (exercise)
│   ├── Algebra Study Guide (document)
│   └── Mathematics Podcast (audio)
└── Sample Audio Resource (audio, no license)
```

## Fixture Files

### Main Test Fixtures
- `content_test.json` - Primary fixture used by most tests
- `channel_test.json` - Channel-specific testing
- `content_import_test.json` - Source fixture for schema generation

### Schema Version Fixtures
- `1_content_data.json` through `5_content_data.json` - Historic schema versions
- `unversioned_content_data.json` - Legacy unversioned schema
- `v0.2.0-beta1_content_data.json`, `v0.4.0-beta3_content_data.json` - Beta version schemas

Each schema version fixture contains the same content tree with only the fields that existed in that schema version.

## Migrating Historic Fixtures

To apply realistic content to all fixtures:

```bash
# Run the migration script
python kolibri/core/content/test/migrate_historic_fixtures.py
```

This script:
1. Generates realistic content using ChannelBuilder
2. For each historic fixture:
   - Infers the schema from the existing fixture
   - Transforms the new content to match the old schema
   - Preserves all IDs, relationships, and structure
3. Writes migrated fixtures back to disk

### Migration Output

Before:
```json
{
  "title": "c1",
  "description": "balbla2",
  "author": "",
  "license_name": "WTFPL"
}
```

After:
```json
{
  "title": "Introduction to Algebra",
  "description": "Learn fundamental algebraic concepts including variables, expressions, and basic equation solving",
  "author": "Kolibri Content Team",
  "license_name": "CC BY"
}
```

## Generating New Schema Fixtures

When creating a new schema version:

```bash
python manage.py generate_schema 6
```

This will:
1. Dynamically register the content schema models
2. Inject those models into ChannelBuilder
3. Generate realistic content using the preset
4. Export using Django's dumpdata command

To use the old behavior (loading from `content_import_test.json`):

```bash
python manage.py generate_schema 6 --use-existing-fixture
```

## Using Fixtures in Tests

### With Django Fixtures (Fast)

```python
class MyTestCase(TestCase):
    fixtures = ["content_test.json"]

    def test_something(self):
        # Descriptive query
        video = ContentNode.objects.get(title="Introduction to Algebra")

        # Or use the specific ID
        video = ContentNode.objects.get(id="32a941fb77c2576e8f6b294cde4c3b0c")
```

### With Dynamic Generation (Flexible)

```python
class MyTestCase(TestCase):
    def setUp(self):
        # Generate custom test data
        builder = ChannelBuilder(levels=5, num_children=10, realistic=True)
        builder.insert_into_default_db()

    def test_large_tree(self):
        # Test with dynamically generated data
        nodes = ContentNode.objects.all()
```

### Hybrid Approach

```python
class MyTestCase(TestCase):
    fixtures = ["content_test.json"]  # Fast base data

    def setUp(self):
        # Add more data dynamically as needed
        builder = ChannelBuilder(levels=2, num_children=3)
        builder.insert_into_default_db()
```

## When to Regenerate Fixtures

Regenerate fixtures when:
- Content models schema changes
- Adding new content types or fields
- Need different test scenarios
- Updating to a new schema version

## Development Workflow

1. **Make changes** to `fixture_presets.py` to define new content trees
2. **Regenerate source fixture**:
   ```bash
   python kolibri/core/content/test/regenerate_source_fixture.py
   ```
3. **Run migration** to update all schema versions:
   ```bash
   python kolibri/core/content/test/migrate_historic_fixtures.py
   ```
4. **Test**: `pytest kolibri/core/content/test/`
5. **Review**: `git diff kolibri/core/content/fixtures/`
6. **Commit** both preset code and generated fixtures

## Architecture Benefits

✓ **Single source of truth**: All fixtures generated from ChannelBuilder presets
✓ **Realistic test data**: Meaningful content improves test readability
✓ **Schema compatibility**: Automatic transformation to match historic schemas
✓ **Easy maintenance**: Regenerate all fixtures with one command
✓ **Flexible testing**: Use fixtures for speed or dynamic generation for flexibility
