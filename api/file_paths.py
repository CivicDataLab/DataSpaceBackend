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


def _organization_file_directory_path(org, filename):
    """
    Create a directory path to upload the sample data file.

    """

    org_name = org.title
    _, extension = os.path.splitext(filename)
    return f"files/resources/{org_name}/sample_data/{extension[1:]}/{filename}"


def _cdo_notification_directory_path(org, filename):
    """
    Create a directory path to upload the notifications file by CDO.

    """

    org_name = org.organization_ptr_id
    _, extension = os.path.splitext(filename)
    return f"files/public/organizations/{org_name}/notifications/{extension[1:]}/{filename}"


def _cdo_notification_hist_directory_path(org, filename):
    """
    Create a directory path to upload the notifications file by CDO.

    """

    org_name = org.org_id.id
    dpa_name = org.new_dpa
    _, extension = os.path.splitext(filename)
    return f"files/public/organizations/{org_name}/notifications_hist/{dpa_name}/{extension[1:]}/{filename}"


def _resource_directory_path(file_details, filename):
    """
    Create a directory path to upload the resources.

    """
    dataset_name = file_details.resource.dataset.title
    resource_name = file_details.resource.title
    file_details.source_file_name = filename
    _, extension = os.path.splitext(filename)
    new_name = str(uuid.uuid4()) + extension
    return f"files/resources/{dataset_name}/{resource_name}/{extension[1:]}/{new_name}"


def _info_directory_path(info, filename):
    """
    Create a directory path to upload additional info.

    """
    dataset_name = info.dataset.title
    resource_name = info.title
    _, extension = os.path.splitext(filename)
    return f"files/info/{dataset_name}/{resource_name}/{extension[1:]}/{filename}"


def _contract_directory_path(dam, filename):
    """
    Create a directory path to upload DAM contract files.

    """
    if dam.organization:
        org_name = dam.organization.title
    else:
        org_name = f'global_dam/{dam.id}'
    dam_name = dam.title
    _, extension = os.path.splitext(filename)
    return f"files/info/{org_name}/{dam_name}/{extension[1:]}/{filename}"


def _license_directory_path(license, filename):
    """
    Create a directory path to upload license files.

    """
    license_name = license.title
    _, extension = os.path.splitext(filename)
    return f"files/info/{license_name}/{extension[1:]}/{filename}"


def _policy_directory_path(policy, filename):
    """
    Create a directory path to upload license files.

    """
    policy_name = policy.title
    _, extension = os.path.splitext(filename)
    return f"files/info/{policy_name}/{extension[1:]}/{filename}"


def _policy_meta_directory_path(policy, filename):
    """
    Create a directory path to upload license files.

    """
    policy_name = policy.title
    _, extension = os.path.splitext(filename)
    return f"files/policy/meta/{policy_name}/{extension[1:]}/{filename}"


def _license_meta_directory_path(policy, filename):
    """
    Create a directory path to upload license files.

    """
    policy_name = policy.title
    _, extension = os.path.splitext(filename)
    return f"files/license/meta/{policy_name}/{extension[1:]}/{filename}"


def _data_request_directory_path(request, filename):
    """
    Create a directory path to receive the request data.

    """
    _, extension = os.path.splitext(filename)
    return f"files/request/{request.id}/{extension[1:]}/{filename}"


def _agreement_directory_path(agreement, filename):
    """
    Create a directory path to receive the agreement.

    """
    _, extension = os.path.splitext(filename)
    return f"files/request/{agreement.id}/{extension[1:]}/{filename}"


def _draft_agreement_directory_path(dam, filename):
    """
    Create a directory path to receive the draft agreement.

    """
    _, extension = os.path.splitext(filename)
    return f"files/draft_agreements/{dam.dataset.catalog.organization.title}/{dam.id}/{extension[1:]}/{filename}"


def _provider_agreement_directory_path(dataset, filename):
    """
    Create a directory path for agreement between dataprovider and IDP.

    """
    _, extension = os.path.splitext(filename)
    return f"files/dataset/{dataset.id}/{extension[1:]}/{filename}"
