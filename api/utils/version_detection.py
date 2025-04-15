import json
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Set, Tuple, Union

import pandas as pd
import structlog
from deepdiff import DeepDiff  # type: ignore

logger = structlog.getLogger(__name__)


def detect_version_change_type(old_file_path: str, new_file_path: str) -> str:
    """
    Analyze changes between two versions of a file and determine the appropriate
    version increment type (major, minor, or patch).

    Args:
        old_file_path: Path to the previous version of the file
        new_file_path: Path to the new version of the file

    Returns:
        String indicating the type of version change: "major", "minor", or "patch"
    """
    # Get file extensions
    _, old_ext = os.path.splitext(old_file_path)
    _, new_ext = os.path.splitext(new_file_path)

    # If file format changed, it's a major change
    if old_ext.lower() != new_ext.lower():
        logger.info(
            f"File format changed from {old_ext} to {new_ext} - major version change"
        )
        return "major"

    # Handle different file types
    if old_ext.lower() in [".csv", ".tsv"]:
        return _detect_tabular_changes(old_file_path, new_file_path)
    elif old_ext.lower() in [".json"]:
        return _detect_json_changes(old_file_path, new_file_path)
    elif old_ext.lower() in [".xml"]:
        return _detect_xml_changes(old_file_path, new_file_path)
    else:
        # For other file types, default to comparing file size
        return _detect_generic_changes(old_file_path, new_file_path)


def _detect_tabular_changes(old_file_path: str, new_file_path: str) -> str:
    """
    Detect changes in tabular data files (CSV, TSV) using pandas
    """
    try:
        # Read files with pandas
        old_df = pd.read_csv(old_file_path, encoding="utf-8")
        new_df = pd.read_csv(new_file_path, encoding="utf-8")

        # Check for schema changes
        old_columns = set(old_df.columns)
        new_columns = set(new_df.columns)

        # If columns were added or removed, it's a major change
        if old_columns != new_columns:
            added = new_columns - old_columns
            removed = old_columns - new_columns
            logger.info(
                f"Schema changed - added columns: {added}, removed columns: {removed} - major version change"
            )
            return "major"

        # Check for data type changes in columns
        for col in old_columns:
            if old_df[col].dtype != new_df[col].dtype:
                logger.info(
                    f"Data type changed for column {col} - major version change"
                )
                return "major"

        # Check for significant row count changes
        if len(old_df) != len(new_df):
            # Row count changed by more than 10%
            change_percentage = (
                abs(len(new_df) - len(old_df)) / max(len(old_df), 1) * 100
            )
            if change_percentage > 10:
                logger.info(
                    f"Row count changed by {change_percentage:.2f}% - minor version change"
                )
                return "minor"

        # Use pandas built-in comparison for data changes
        # Limit to common rows to avoid index errors
        min_rows = min(len(old_df), len(new_df))
        if min_rows > 0:
            # Truncate both dataframes to the same length
            old_sample = old_df.iloc[:min_rows].reset_index(drop=True)
            new_sample = new_df.iloc[:min_rows].reset_index(drop=True)

            # Use pandas compare function (available in pandas >= 1.1.0)
            try:
                # Get differences between dataframes
                diff_df = new_sample.compare(old_sample)

                # Calculate change percentage
                total_cells = min_rows * len(old_columns)
                changed_cells = diff_df.size  # Number of changed cells

                change_percentage = (
                    (changed_cells / total_cells) * 100 if total_cells > 0 else 0
                )

                if change_percentage > 30:
                    logger.info(
                        f"Data changed significantly ({change_percentage:.2f}% of cells) - minor version change"
                    )
                    return "minor"
                elif change_percentage > 0:
                    logger.info(
                        f"Small data changes ({change_percentage:.2f}% of cells) - patch version change"
                    )
                    return "patch"
            except Exception as compare_error:
                # Fallback if compare fails (older pandas version or other issues)
                logger.warning(
                    f"Pandas compare failed: {str(compare_error)}, using manual comparison"
                )

                # Manual comparison as fallback
                changes = 0
                total_cells = min_rows * len(old_columns)

                for col in old_columns:
                    # Compare column values
                    unequal_mask = old_sample[col].values != new_sample[col].values
                    changes += unequal_mask.sum()  # type: ignore

                change_percentage = (
                    (changes / total_cells) * 100 if total_cells > 0 else 0
                )

                if change_percentage > 30:
                    logger.info(
                        f"Data changed significantly ({change_percentage:.2f}% of cells) - minor version change"
                    )
                    return "minor"
                elif change_percentage > 0:
                    logger.info(
                        f"Small data changes ({change_percentage:.2f}% of cells) - patch version change"
                    )
                    return "patch"

        # Default to patch for minimal changes
        return "patch"

    except Exception as e:
        logger.error(f"Error analyzing tabular files: {str(e)}")
        # Default to minor if we can't analyze properly
        return "minor"


def _detect_json_changes(old_file_path: str, new_file_path: str) -> str:
    """
    Detect changes in JSON files using DeepDiff
    """
    try:
        with open(old_file_path, "r", encoding="utf-8") as f:
            old_data = json.load(f)

        with open(new_file_path, "r", encoding="utf-8") as f:
            new_data = json.load(f)

        # Use DeepDiff for efficient and accurate comparison
        diff = DeepDiff(old_data, new_data, ignore_order=True)

        # Check for structure changes (major)
        if diff.get("dictionary_item_added") or diff.get("dictionary_item_removed"):
            logger.info(f"JSON structure changed - major version change")
            return "major"

        # Check for type changes (major)
        if diff.get("type_changes"):
            logger.info(f"JSON data types changed - major version change")
            return "major"

        # Check for significant value changes (minor)
        value_changes = len(diff.get("values_changed", {}))
        if isinstance(old_data, dict) and isinstance(new_data, dict):
            total_values = _count_values(old_data)
            change_percentage = (
                (value_changes / total_values) * 100 if total_values > 0 else 0
            )

            if change_percentage > 30:
                logger.info(
                    f"JSON values changed significantly ({change_percentage:.2f}%) - minor version change"
                )
                return "minor"

        # Check for array changes (minor)
        if diff.get("iterable_item_added") or diff.get("iterable_item_removed"):
            logger.info(f"JSON array items changed - minor version change")
            return "minor"

        # If there are any changes at all, it's at least a patch
        if diff:
            return "patch"

        # No changes detected
        return "patch"

    except Exception as e:
        logger.error(f"Error analyzing JSON files: {str(e)}")
        return "minor"


def _detect_xml_changes(old_file_path: str, new_file_path: str) -> str:
    """
    Detect changes in XML files
    """
    try:
        import xml.etree.ElementTree as ET

        old_tree = ET.parse(old_file_path)
        new_tree = ET.parse(new_file_path)

        old_root = old_tree.getroot()
        new_root = new_tree.getroot()

        # Check for tag changes
        old_tags = _get_xml_tags(old_root)
        new_tags = _get_xml_tags(new_root)

        if old_tags != new_tags:
            logger.info(f"XML structure changed - major version change")
            return "major"

        # Check for attribute changes
        old_attrs = _get_xml_attributes(old_root)
        new_attrs = _get_xml_attributes(new_root)

        if old_attrs != new_attrs:
            logger.info(f"XML attributes changed - minor version change")
            return "minor"

        # Default to patch for content changes
        return "patch"

    except Exception as e:
        logger.error(f"Error analyzing XML files: {str(e)}")
        return "minor"


def _detect_generic_changes(old_file_path: str, new_file_path: str) -> str:
    """
    Detect changes in generic files based on size
    """
    old_size = os.path.getsize(old_file_path)
    new_size = os.path.getsize(new_file_path)

    # Calculate size change percentage
    size_change_percentage = abs(new_size - old_size) / max(old_size, 1) * 100

    if size_change_percentage > 50:
        logger.info(
            f"File size changed by {size_change_percentage:.2f}% - major version change"
        )
        return "major"
    elif size_change_percentage > 10:
        logger.info(
            f"File size changed by {size_change_percentage:.2f}% - minor version change"
        )
        return "minor"
    else:
        logger.info(
            f"File size changed by {size_change_percentage:.2f}% - patch version change"
        )
        return "patch"


def _flatten_dict_keys(d: Dict, parent_key: str = "") -> List[str]:
    """
    Flatten nested dictionary keys
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict_keys(v, new_key))
        else:
            items.append(new_key)
    return items


def _count_values(obj: Union[Dict, List, Any], count: int = 0) -> int:
    """
    Count the total number of values in a nested structure
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            count += 1  # Count the key-value pair itself
            if isinstance(v, (dict, list)):
                count = _count_values(v, count)
    elif isinstance(obj, list):
        count += len(obj)  # Count the list items
        for item in obj:
            if isinstance(item, (dict, list)):
                count = _count_values(item, count)
    return count


def _get_xml_tags(element: ET.Element) -> Set[str]:
    """
    Get all unique tag names in an XML tree
    """
    tags = {element.tag}
    for child in element:
        tags.update(_get_xml_tags(child))
    return tags


def _get_xml_attributes(element: ET.Element) -> Set[Tuple[str, str]]:
    """
    Get all attributes in an XML tree as (element_tag, attribute_name) pairs
    """
    attrs = {(element.tag, attr) for attr in element.attrib.keys()}
    for child in element:
        attrs.update(_get_xml_attributes(child))
    return attrs
