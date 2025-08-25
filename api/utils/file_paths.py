import os
import uuid
from typing import Any


def _organization_directory_path(org: Any, filename: str) -> str:
    """
    Create a directory path to upload the organization logo

    """

    org_name = org.name
    _, extension = os.path.splitext(filename)
    return f"files/public/organizations/{org_name}/{extension[1:]}/{filename}"


def _chart_image_directory_path(chart: Any, filename: str) -> str:
    """
    Create a directory path to upload the organization logo

    """

    chart_name = chart.name
    _, extension = os.path.splitext(filename)
    return f"files/chart_images/{chart_name}/{extension[1:]}/{filename}"


def _dataspace_directory_path(ds: Any, filename: str) -> str:
    """
    Create a directory path to upload the dataspace logo

    """

    ds_name = ds.name
    _, extension = os.path.splitext(filename)
    return f"files/public/dataspace/{ds_name}/{extension[1:]}/{filename}"


def _use_case_directory_path(uc: Any, filename: str) -> str:
    """
    Create a directory path to upload the use case logo

    """

    uc_name = uc.title
    _, extension = os.path.splitext(filename)
    return f"files/use_case/{uc_name}/logo/{filename}"


def _user_profile_image_directory_path(user: Any, filename: str) -> str:
    """
    Create a directory path to upload the user profile image

    """
    user_name = user.keycloak_id
    _, extension = os.path.splitext(filename)
    return f"files/user_profile/{user_name}/{extension[1:]}/{filename}"


def _organization_file_directory_path(org: Any, filename: str) -> str:
    """
    Create a directory path to upload the sample data file.

    """

    org_name = org.name
    _, extension = os.path.splitext(filename)
    return f"files/resources/{org_name}/sample_data/{extension[1:]}/{filename}"


def _catalog_directory_path(catalog: Any, filename: str) -> str:
    """
    Create a directory path to upload the catalog logo
    """
    catalog_name = catalog.name
    _, extension = os.path.splitext(filename)
    return f"files/catalog/{catalog_name}/{extension[1:]}/{filename}"
