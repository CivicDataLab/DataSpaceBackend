from typing import Any, Dict, List, Optional, cast

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart


@register_chart("MULTILINE")
class MultiLineChart(BaseChart):

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for line chart."""
        base_opts = super().get_chart_specific_opts()

        # Configure x-axis labels
        base_opts["xaxis_opts"].axislabel_opts = opts.LabelOpts(
            rotate=45, interval=0, margin=8
        )

        # Add line chart specific options
        y_axis_columns = self._get_y_axis_columns()
        base_opts.update(
            {
                "datazoom_opts": [
                    opts.DataZoomOpts(
                        is_show=True, type_="slider", range_start=0, range_end=100
                    ),
                    opts.DataZoomOpts(type_="inside"),
                ],
                "visualmap_opts": (
                    opts.VisualMapOpts(
                        is_show=False,
                        type_="continuous",
                        min_=0,
                        max_=len(y_axis_columns) - 1,
                    )
                    if len(y_axis_columns) > 1
                    else None
                ),
            }
        )
        return base_opts

    def get_init_opts(self) -> opts.InitOpts:
        """Override to provide line chart specific initialization options."""
        return opts.InitOpts(
            width=self.options.get("width", "100%"),
            height=self.options.get("height", "400px"),
            theme=self.options.get("theme", "white"),
        )

    def get_series_style_opts(self, color: Optional[str] = None) -> Dict[str, Any]:
        """Get line chart specific styling options."""
        # Line chart specific options
        return {
            "itemstyle_opts": opts.ItemStyleOpts(color=color) if color else None,
            "linestyle_opts": opts.LineStyleOpts(width=2, type_="solid"),
            "is_smooth": True,
            "is_symbol_show": True,
        }
