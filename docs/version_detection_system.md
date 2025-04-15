# Intelligent Version Detection System

## Overview

The DataSpace platform implements an version detection system that automatically determines the appropriate version increment (major, minor, or patch) when resources are updated. This document explains the technical implementation, triggering mechanisms, and version classification logic.

## Version Increment Types

The system follows semantic versioning principles (X.Y.Z):

1. **Major Version (X)**: Breaking changes or significant structural modifications
2. **Minor Version (Y)**: Publishing Dataset or significant data changes that maintain compatibility
3. **Patch Version (Z)**: Small fixes, corrections, or minimal data changes

## Triggering Mechanisms

Version changes are automatically triggered by the following events:

1. **Resource File Updates**: When a resource file is updated through the API
2. **Dataset Publication**: When a dataset containing resources is published
3. **Manual Triggers**: Through management commands (e.g., `create_major_version`)

## Technical Implementation

### Components

1. **Signal Handlers**: Detect changes to resources and trigger version detection
2. **Version Detection Utility**: Analyzes file changes to determine version increment type
3. **DVC Manager**: Handles version tracking, tagging, and remote storage

### Signal Flow

```
ResourceFileDetails update → post_save signal → version_resource_with_dvc
    → detect_version_change_type → _increment_version → Create ResourceVersion
```

## Change Detection Logic

The system uses different strategies based on file type:

### CSV/Tabular Files

**Major Version** triggers:
- Schema changes (columns added/removed)
- Data type changes in columns

**Minor Version** triggers:
- Row count changes > 10%
- Data changes in > 30% of cells

**Patch Version** triggers:
- Small data changes (< 30% of cells)
- Minimal corrections

### JSON Files

**Major Version** triggers:
- Structure changes (keys added/removed)
- Data type changes

**Minor Version** triggers:
- Significant value changes (> 30% of values)
- Array item additions/removals

**Patch Version** triggers:
- Small value changes
- Formatting changes

### XML Files

**Major Version** triggers:
- Tag structure changes

**Minor Version** triggers:
- Attribute changes

**Patch Version** triggers:
- Content changes without structural modifications

### Generic Files

For non-structured files, the system uses file size differences:

**Major Version** triggers:
- Size changes > 50%

**Minor Version** triggers:
- Size changes between 10% and 50%

**Patch Version** triggers:
- Size changes < 10%

## Technical Details

### Dependencies

- **pandas**: For efficient tabular data comparison
- **DeepDiff**: For accurate JSON structure comparison
- **DVC**: For version tracking and storage

### Performance Considerations

- Large files (>100MB) use chunked processing
- Tabular comparisons use sampling for very large datasets
- Early return logic to avoid unnecessary processing

## Example

When a CSV resource is updated:

1. The system detects the change through a Django signal
2. `detect_version_change_type` loads both versions of the file
3. The function compares schemas, data types, and values
4. Based on the extent of changes, it returns "major", "minor", or "patch"
5. The version is incremented accordingly (e.g., 1.2.3 → 1.3.0 for minor)
6. DVC tracks the new version with appropriate tags
7. A ResourceVersion record is created in the database

## Management Commands

The system includes management commands for manual version control:

- `create_major_version`: Force a major version increment for a resource
- `setup_dvc`: Configure DVC repository and remotes

## Error Handling

The version detection system includes robust error handling to ensure that:

1. Failed comparisons default to "minor" version changes
2. Temporary files are properly cleaned up
3. Errors are logged with detailed context
4. The system continues functioning even if analysis fails

## Future Improvements

- Support for more file formats
- Configurable thresholds for different file types
- Performance optimizations for very large datasets
