CHART_REGISTRY = {}


def register_chart(chart_type: str):
    def decorator(cls):
        CHART_REGISTRY[chart_type] = cls
        return cls

    return decorator
