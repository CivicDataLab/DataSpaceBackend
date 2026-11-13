"""Every reader of data tables still works on the new per-upload tables.

The readers look the table up from the resource's ResourceDataTable row, so
the new names should be invisible to them. This proves it for each reader,
on a header with a percent sign (common in indicator tables).
"""

from typing import Any

from api.models import ResourcePreviewDetails, ResourceSchema
from api.utils.data_indexing import (
    fetch_resource_data,
    get_preview_data,
    get_resource_columns,
    get_row_count,
    index_resource_data,
    query_resource_data,
)
from tests.data_index.support import uses_data_db

COLUMNS = ["district", "Literacy rate (%)", "year"]


@uses_data_db
def test_every_reader_works_on_a_new_table_with_a_percent_header(add_resource: Any) -> None:
    resource = add_resource("literacy.csv", "percent_header.csv")
    resource.preview_enabled = True
    resource.preview_details = ResourcePreviewDetails.objects.create(is_all_entries=True)
    resource.save()
    row = index_resource_data(resource)
    assert row is not None and row.table_name.startswith("rdt_")

    assert get_row_count(resource) == 3

    preview = get_preview_data(resource)
    assert preview is not None
    assert preview.columns == COLUMNS
    assert len(preview.rows) == 3

    assert get_resource_columns(resource) == COLUMNS

    fetched = fetch_resource_data(
        resource,
        filters={"Literacy rate (%)__gte": 80},
        columns=["district", "Literacy rate (%)"],
        order_by=["-Literacy rate (%)"],
    )
    assert fetched["rows"] == [["Jorhat", 85.25], ["Kamrup", 81.5]]
    assert fetched["total"] == 2

    chart = query_resource_data(
        resource, 'SELECT district, "Literacy rate (%)" FROM {{table}} WHERE year = 2022'
    )
    assert chart is not None
    assert chart.values.tolist() == [["Jorhat", 85.25]]

    # With no column rows, the column list falls back to the table itself.
    ResourceSchema.objects.filter(resource=resource).delete()
    assert get_resource_columns(resource) == COLUMNS
