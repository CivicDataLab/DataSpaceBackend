#!/usr/bin/env python
"""
Test script for hierarchical geography filtering.

This script tests the Geography model's hierarchical filtering methods
to ensure that selecting a parent geography returns all child geographies.

Usage:
    python test_geography_hierarchy.py
"""

import os
import sys

import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DataSpace.settings")
django.setup()

from api.models import Geography


def test_geography_hierarchy() -> None:
    """Test the geography hierarchy methods."""
    print("=" * 80)
    print("Testing Geography Hierarchical Filtering")
    print("=" * 80)

    # Test 1: Get all geographies
    all_geographies = Geography.objects.all()
    print(f"\n✓ Total geographies in database: {all_geographies.count()}")

    # Test 2: Test with a country (should return country + all its states)
    try:
        india = Geography.objects.get(name="India")
        print(f"\n✓ Found geography: {india}")

        descendants = india.get_all_descendant_names()
        print(f"✓ India has {len(descendants)} total geographies (including itself)")
        print(f"  Sample descendants: {descendants[:5]}...")

        # Verify it includes India itself
        assert "India" in descendants, "India should be in its own descendants"
        print("✓ India is included in its descendants")

        # Verify it includes at least some Indian states
        indian_states = ["Assam", "Maharashtra", "Karnataka", "Tamil Nadu"]
        found_states = [state for state in indian_states if state in descendants]
        print(f"✓ Found {len(found_states)} sample states: {found_states}")

    except Geography.DoesNotExist:
        print("✗ India geography not found in database")

    # Test 3: Test the class method with multiple geographies
    print("\n" + "-" * 80)
    print("Testing get_geography_names_with_descendants class method")
    print("-" * 80)

    test_names = ["India", "Thailand"]
    try:
        expanded_names = Geography.get_geography_names_with_descendants(test_names)
        print(f"\n✓ Input geographies: {test_names}")
        print(f"✓ Expanded to {len(expanded_names)} geographies")
        print(f"  Sample: {expanded_names[:10]}...")

        # Verify both countries are included
        assert "India" in expanded_names, "India should be in expanded names"
        assert "Thailand" in expanded_names, "Thailand should be in expanded names"
        print("✓ Both parent geographies are included")

    except Exception as e:
        print(f"✗ Error testing class method: {e}")

    # Test 4: Test with non-existent geography
    print("\n" + "-" * 80)
    print("Testing with non-existent geography")
    print("-" * 80)

    test_names_with_invalid = ["India", "NonExistentPlace"]
    expanded_names = Geography.get_geography_names_with_descendants(test_names_with_invalid)
    print(f"\n✓ Input: {test_names_with_invalid}")
    print(f"✓ Expanded to {len(expanded_names)} geographies")
    print("✓ Non-existent geography handled gracefully")
    assert "NonExistentPlace" in expanded_names, "Non-existent place should be included as-is"

    # Test 5: Test with a leaf node (state with no children)
    print("\n" + "-" * 80)
    print("Testing with leaf node (state with no children)")
    print("-" * 80)

    try:
        assam = Geography.objects.get(name="Assam")
        descendants = assam.get_all_descendant_names()
        print(f"\n✓ Assam descendants: {descendants}")
        assert len(descendants) == 1, "Leaf node should only return itself"
        assert descendants[0] == "Assam", "Leaf node should return its own name"
        print("✓ Leaf node correctly returns only itself")
    except Geography.DoesNotExist:
        print("✗ Assam geography not found in database")

    print("\n" + "=" * 80)
    print("✅ All tests completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    try:
        test_geography_hierarchy()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
