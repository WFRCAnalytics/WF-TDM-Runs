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

First cut of this only repositioned the legend (SLIDE_LEGEND's y=1.02
alone), which then collided with the chart's own title for any chart that
has both an in-plot title (title=dict(text=...)) and a visible legend --
title and legend both landed in the same cramped band just above the plot
area. Fixed by also pinning the title near the very top of the figure
(TITLE_DEFAULTS) and reserving enough top margin (MARGIN_DEFAULTS) for
both, verified against single-line and two-line (title+<br><sup>subtitle)
titles alike.
"""
import plotly.graph_objects as go
import plotly.io as pio

# Legend: a horizontal band top-left (clear of Plotly's top-right modebar),
# floated high enough (y=1.1) to clear the title below it.
SLIDE_LEGEND = dict(orientation="h", yanchor="bottom", y=1.1, xanchor="left", x=0)

# Title: pinned near the very top of the figure so it has a fixed, known
# position regardless of legend/margin -- font_size is left to each chart.
SLIDE_TITLE = dict(y=0.97, yanchor="top")

# Enough reserved top margin for a two-line title (text + <br><sup>subtitle)
# plus the legend band above it, without either being clipped or cramped.
SLIDE_MARGIN = dict(t=90)


def use_slide_chart_defaults():
    """Call once, in a slides.qmd's setup cell, after importing
    plotly.express -- registers a Plotly template giving every
    subsequently-created figure in this document a top-left legend, a
    pinned title position, and reserved top margin by default, so title and
    legend don't compete for the same space. A chart can still override any
    of this further (e.g. legend=dict(y=1.15) for an extra-tall title) or
    turn the legend off entirely (showlegend=False); this only sets what
    happens if it doesn't -- an explicit per-chart value always wins over
    the template default."""
    pio.templates["wfrc_slide_legend"] = go.layout.Template(
        layout=go.Layout(legend=SLIDE_LEGEND, title=SLIDE_TITLE, margin=SLIDE_MARGIN)
    )
    pio.templates.default = "plotly+wfrc_slide_legend"
