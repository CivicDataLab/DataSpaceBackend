from typing import Callable, Dict, Optional, Type

from api.types.charts.base_chart import BaseChart

CHART_REGISTRY: Dict[str, Type[BaseChart]] = {}


def register_chart(chart_type: str) -> Callable[[Type[BaseChart]], Type[BaseChart]]:
    """Register a chart class for a given chart type."""

    def decorator(chart_class: Type[BaseChart]) -> Type[BaseChart]:
        CHART_REGISTRY[chart_type] = chart_class
        return chart_class

    return decorator


def get_chart_class(chart_type: str) -> Optional[Type[BaseChart]]:
    """Get the chart class for a given chart type."""
    return CHART_REGISTRY.get(chart_type)
