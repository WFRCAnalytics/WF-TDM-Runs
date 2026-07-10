"""Shared Plotly chart-styling helpers for every run_set's report pages
(reports/run_sets/<id>/summary.qmd and slides.qmd).

use_slide_chart_defaults() exists because Plotly Express's default chart
legend sits top-right, outside the plot -- fine on a full-width HTML page
(summary.qmd), but colliding with Plotly's own modebar icons (also
top-right) on a RevealJS slide deck's narrow, fixed-size canvas. This same
collision was independently hand-fixed per-chart twice now
(non-motorized-2023/slides.qmd, then bring-work-trips-closer-to-home/
slides.qmd) by adding an identical legend=dict(...) override to every
affected fig.update_layout() call. Centralized here so a new slides.qmd
only needs one setup-cell call instead of that being rediscovered per chart.
"""
import plotly.graph_objects as go
import plotly.io as pio

# Position only -- font_size and any per-chart y offset (e.g. a taller
# multi-line title needing more clearance) are left to each chart's own
# update_layout() call, which merges on top of this rather than replacing it.
SLIDE_LEGEND = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)


def use_slide_chart_defaults():
    """Call once, in a slides.qmd's setup cell, after importing
    plotly.express -- registers a Plotly template that gives every
    subsequently-created figure in this document SLIDE_LEGEND's top-left
    horizontal legend by default. A chart can still override position
    further (e.g. legend=dict(y=1.08)) or turn the legend off entirely
    (showlegend=False); this only sets what happens if it doesn't."""
    pio.templates["wfrc_slide_legend"] = go.layout.Template(layout=go.Layout(legend=SLIDE_LEGEND))
    pio.templates.default = "plotly+wfrc_slide_legend"
