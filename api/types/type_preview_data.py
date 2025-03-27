from typing import List

import strawberry
from strawberry.scalars import JSON


@strawberry.type
class PreviewData:
    """Type for preview data."""

    columns: List[str]
    rows: List[List[JSON]]
