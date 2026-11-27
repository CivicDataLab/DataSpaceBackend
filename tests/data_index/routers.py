"""Keep Django's own tables out of the test data database.

In production the data database holds only data tables (one per tabular
upload). The router mirrors that in tests, so pytest-django creates no model
tables there and an orphan or "is this the main database?" check sees what
production would see.
"""

from typing import Any, Optional


class DataDbTestRouter:
    def allow_migrate(
        self, db: str, app_label: str, model_name: Optional[str] = None, **hints: Any
    ) -> Optional[bool]:
        if db == "data_db":
            return False
        return None
