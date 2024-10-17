import os
import uuid


def _organization_directory_path(org, filename):
    """
    Create a directory path to upload the organization logo

    """

    org_name = org.title
    _, extension = os.path.splitext(filename)
    return f"files/public/organizations/{org_name}/{extension[1:]}/{filename}"


def _dataspace_directory_path(ds, filename):
    """
    Create a directory path to upload the dataspace logo

    """

    ds_name = ds.name
    _, extension = os.path.splitext(filename)
    return f"files/public/dataspace/{ds_name}/{extension[1:]}/{filename}"


def _use_case_directory_path(uc, filename):
    """
    Create a directory path to upload the use case logo

    """

    uc_name = uc.title
    _, extension = os.path.splitext(filename)
    return f"files/use_case/{uc_name}/logo/{filename}"


def _organization_file_directory_path(org, filename):
    """
    Create a directory path to upload the sample data file.

    """

    org_name = org.title
    _, extension = os.path.splitext(filename)
    return f"files/resources/{org_name}/sample_data/{extension[1:]}/{filename}"
