"""Drop a data table once the row that points at it is deleted.

Re-uploads, resource deletes, dataset deletes (by cascade) and admin deletes
all delete the resource's ResourceDataTable row, so this one receiver frees the
storage for every one of them. The drop waits for the delete to commit, so a
rolled-back delete keeps its data, and it leaves a legacy table alone while
another row still shares it.

Registered in api/signals/__init__.py (a test proves it is connected once the
app loads). Docs: ../utils/data_indexing_architecture.md
"""

from functools import partial
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from api.models.Resource import ResourceDataTable
from api.utils.data_tables import drop_data_table_if_unshared


@receiver(post_delete, sender=ResourceDataTable)
def drop_table_after_row_delete(
    sender: Any, instance: ResourceDataTable, using: str, **kwargs: Any
) -> None:
    # Once the delete commits, drop the row's table (unless another row still uses it).
    transaction.on_commit(
        partial(drop_data_table_if_unshared, instance.table_name, instance.pk),
        using=using,
        robust=True,
    )
