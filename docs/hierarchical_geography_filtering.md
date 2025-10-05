# Hierarchical Geography Filtering

## Overview

The DataSpace platform now supports hierarchical geography filtering for datasets and use cases. When a parent geography (e.g., a country) is selected as a filter, the search results will automatically include entities tagged with any child geographies (e.g., states/provinces within that country).

## How It Works

### Geography Hierarchy Structure

The geography data is organized hierarchically:
- **Region** (e.g., Asia Pacific)
  - **Country** (e.g., India, Thailand, Indonesia)
    - **State/Province** (e.g., Assam, Maharashtra, Bangkok)

### Filtering Behavior

**Before:** Selecting "India" as a geography filter would only return datasets/use cases explicitly tagged with "India".

**After:** Selecting "India" as a geography filter now returns:
- Datasets/use cases tagged with "India"
- Datasets/use cases tagged with any Indian state (Assam, Maharashtra, Karnataka, etc.)

This makes it easier to discover all relevant content for a geographic region without having to select each child geography individually.

## Implementation Details

### Backend Changes

#### 1. Geography Model (`api/models/Geography.py`)

Added two new methods to the `Geography` model:

```python
def get_all_descendant_names(self) -> List[str]:
    """
    Get all descendant geography names including self.
    Returns a list of geography names including self and all descendants.
    """

@classmethod
def get_geography_names_with_descendants(cls, geography_names: List[str]) -> List[str]:
    """
    Given a list of geography names, return all names including their descendants.
    This is a helper method for filtering that expands parent geographies to include children.
    """
```

#### 2. Search Views

Updated both search views to use hierarchical filtering:

**`api/views/search_dataset.py`** - Dataset search
**`api/views/search_usecase.py`** - Use case search

In the `add_filters` method, when processing geography filters:

```python
# For geographies, expand to include all descendant geographies
if filter == "geographies":
    filter_values = Geography.get_geography_names_with_descendants(
        filter_values
    )
```

### API Usage

The API endpoints remain unchanged. The hierarchical filtering is applied automatically on the backend:

**Dataset Search:**
```
GET /api/search/dataset/?geographies=India
```

**Use Case Search:**
```
GET /api/search/usecase/?geographies=Thailand
```

**Multiple Geographies:**
```
GET /api/search/dataset/?geographies=India,Thailand
```

## Examples

### Example 1: Single Parent Geography

**Request:**
```
GET /api/search/dataset/?geographies=India
```

**Behavior:**
- Expands "India" to include all Indian states/UTs (Assam, Maharashtra, Karnataka, etc.)
- Returns datasets tagged with India OR any Indian state

### Example 2: Multiple Geographies

**Request:**
```
GET /api/search/dataset/?geographies=India,Thailand
```

**Behavior:**
- Expands "India" to include all Indian states
- Expands "Thailand" to include all Thai provinces
- Returns datasets tagged with any of these geographies

### Example 3: Child Geography

**Request:**
```
GET /api/search/usecase/?geographies=Assam
```

**Behavior:**
- "Assam" is a leaf node (no children)
- Returns use cases tagged with Assam only
- No expansion occurs

### Example 4: Mixed Parent and Child

**Request:**
```
GET /api/search/dataset/?geographies=India,Bangkok
```

**Behavior:**
- Expands "India" to include all Indian states
- "Bangkok" remains as-is (leaf node)
- Returns datasets tagged with India, any Indian state, or Bangkok

## Testing

### Unit Tests

Comprehensive unit tests are available in `tests/test_geography_hierarchy.py`:

```bash
pytest tests/test_geography_hierarchy.py -v
```

Tests cover:
- Parent geography expansion
- Leaf node behavior
- Multiple geography expansion
- Non-existent geography handling
- Mixed existing/non-existent geographies
- Multi-level hierarchy depth

### Manual Testing

You can test the hierarchy methods directly:

```python
from api.models import Geography

# Get a country
india = Geography.objects.get(name="India")

# Get all descendants (including itself)
descendants = india.get_all_descendant_names()
print(f"India has {len(descendants)} geographies")

# Expand multiple geographies
expanded = Geography.get_geography_names_with_descendants(["India", "Thailand"])
print(f"Expanded to {len(expanded)} geographies")
```

## Performance Considerations

### Recursive Query Optimization

The `get_all_descendant_names()` method uses recursion to traverse the geography tree. For the current dataset (4 countries with ~200 states/provinces total), this is performant.

If the geography hierarchy grows significantly deeper or wider, consider:
1. Adding a caching layer for frequently accessed hierarchies
2. Using Django's `prefetch_related()` for bulk operations
3. Implementing a materialized path or nested set model

### Elasticsearch Impact

The geography expansion happens before the Elasticsearch query is executed, so:
- No changes to Elasticsearch index structure required
- Query performance remains similar (using `terms` filter)
- The expanded list of geography names is passed directly to Elasticsearch

## Backward Compatibility

✅ **Fully backward compatible**

- No API changes required
- Frontend code continues to work without modifications
- Existing geography filters automatically benefit from hierarchical filtering
- No database migrations needed

## Future Enhancements

Potential improvements for future iterations:

1. **Configurable Hierarchy Depth**: Allow API consumers to specify how many levels to expand
2. **Parent Geography Aggregations**: Show parent geographies in faceted search results
3. **Geography Path Display**: Show full hierarchy path (e.g., "Asia Pacific > India > Assam")
4. **Caching**: Cache geography hierarchies for improved performance
5. **Reverse Lookup**: Find parent geographies for a given child

## Related Files

- `api/models/Geography.py` - Geography model with hierarchy methods
- `api/views/search_dataset.py` - Dataset search with hierarchical filtering
- `api/views/search_usecase.py` - Use case search with hierarchical filtering
- `tests/test_geography_hierarchy.py` - Unit tests for hierarchy functionality
- `api/management/commands/populate_geographies.py` - Geography data population

## Support

For questions or issues related to hierarchical geography filtering, please:
1. Check the unit tests for usage examples
2. Review the Geography model implementation
3. Test with the provided test script
4. Contact the development team
