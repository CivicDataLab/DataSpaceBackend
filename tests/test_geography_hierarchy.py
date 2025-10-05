"""
Tests for hierarchical geography filtering functionality.

This module tests the Geography model's methods for hierarchical filtering,
ensuring that selecting a parent geography returns all child geographies.
"""

import pytest

from api.models import Geography
from api.utils.enums import GeoTypes


@pytest.mark.django_db
class TestGeographyHierarchy:
    """Test cases for geography hierarchical filtering."""

    @pytest.fixture
    def sample_geography_hierarchy(self):
        """Create a sample geography hierarchy for testing."""
        # Create region
        region = Geography.objects.create(
            name="Test Region", code="TR", type=GeoTypes.REGION
        )

        # Create country
        country = Geography.objects.create(
            name="Test Country", code="TC", type=GeoTypes.COUNTRY, parent_id=region
        )

        # Create states
        state1 = Geography.objects.create(
            name="Test State 1", code="TS1", type=GeoTypes.STATE, parent_id=country
        )
        state2 = Geography.objects.create(
            name="Test State 2", code="TS2", type=GeoTypes.STATE, parent_id=country
        )

        return {
            "region": region,
            "country": country,
            "state1": state1,
            "state2": state2,
        }

    def test_get_all_descendant_names_with_children(self, sample_geography_hierarchy):
        """Test that a parent geography returns all its descendants."""
        country = sample_geography_hierarchy["country"]
        descendants = country.get_all_descendant_names()

        # Should include the country itself and both states
        assert len(descendants) == 3
        assert "Test Country" in descendants
        assert "Test State 1" in descendants
        assert "Test State 2" in descendants

    def test_get_all_descendant_names_leaf_node(self, sample_geography_hierarchy):
        """Test that a leaf node (no children) returns only itself."""
        state1 = sample_geography_hierarchy["state1"]
        descendants = state1.get_all_descendant_names()

        # Should only include itself
        assert len(descendants) == 1
        assert descendants[0] == "Test State 1"

    def test_get_all_descendant_names_includes_self(self, sample_geography_hierarchy):
        """Test that the geography itself is always included in descendants."""
        region = sample_geography_hierarchy["region"]
        descendants = region.get_all_descendant_names()

        # Should include the region itself
        assert "Test Region" in descendants

    def test_get_geography_names_with_descendants_single(
        self, sample_geography_hierarchy
    ):
        """Test expanding a single geography name to include descendants."""
        expanded = Geography.get_geography_names_with_descendants(["Test Country"])

        # Should include country and both states
        assert len(expanded) == 3
        assert "Test Country" in expanded
        assert "Test State 1" in expanded
        assert "Test State 2" in expanded

    def test_get_geography_names_with_descendants_multiple(
        self, sample_geography_hierarchy
    ):
        """Test expanding multiple geography names."""
        expanded = Geography.get_geography_names_with_descendants(
            ["Test State 1", "Test State 2"]
        )

        # Should include both states (no children, so just themselves)
        assert len(expanded) == 2
        assert "Test State 1" in expanded
        assert "Test State 2" in expanded

    def test_get_geography_names_with_descendants_nonexistent(self):
        """Test handling of non-existent geography names."""
        expanded = Geography.get_geography_names_with_descendants(
            ["NonExistent Geography"]
        )

        # Should include the non-existent name as-is
        assert len(expanded) == 1
        assert "NonExistent Geography" in expanded

    def test_get_geography_names_with_descendants_mixed(
        self, sample_geography_hierarchy
    ):
        """Test expanding a mix of existing and non-existent geographies."""
        expanded = Geography.get_geography_names_with_descendants(
            ["Test Country", "NonExistent Geography"]
        )

        # Should include country, its states, and the non-existent name
        assert len(expanded) == 4
        assert "Test Country" in expanded
        assert "Test State 1" in expanded
        assert "Test State 2" in expanded
        assert "NonExistent Geography" in expanded

    def test_hierarchical_depth(self, sample_geography_hierarchy):
        """Test that hierarchy works at multiple levels."""
        region = sample_geography_hierarchy["region"]
        descendants = region.get_all_descendant_names()

        # Should include region, country, and both states (4 total)
        assert len(descendants) == 4
        assert "Test Region" in descendants
        assert "Test Country" in descendants
        assert "Test State 1" in descendants
        assert "Test State 2" in descendants

    def test_empty_list(self):
        """Test handling of empty geography list."""
        expanded = Geography.get_geography_names_with_descendants([])

        # Should return empty list
        assert len(expanded) == 0
        assert expanded == []
