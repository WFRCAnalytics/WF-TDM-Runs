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
import math

import plotly.graph_objects as go
import plotly.io as pio

# Passed to every fig.show() call (see the .qmd files) to hide Plotly's own
# top-right modebar (zoom/pan/download icons) -- these reports are static,
# view-only pages, not interactive analysis notebooks, so the modebar is
# just clutter (and was already the thing use_slide_chart_defaults()'s
# legend repositioning had to dodge).
CHART_CONFIG = {"displayModeBar": False}

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


def _fixed_range(y_lists, pad_frac=0.08):
    """Common y-axis range spanning every list of y-values in y_lists, with
    symmetric padding -- used so switching figure_with_shift_toggle's
    shift-level (or Absolute/% Change) buttons restyles traces without also
    rescaling the axis, since a rescale on every click makes it hard to
    visually compare magnitudes across shift levels."""
    values = [v for y in y_lists for v in y if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not values:
        return None
    lo, hi = min(values), max(values)
    span = hi - lo
    pad = span * pad_frac if span else (abs(hi) * pad_frac or 1)
    return [lo - pad, hi + pad]


def figure_with_shift_toggle(
    df, build_fig, shift_col="shift_pct", default_shift=10, shift_label_fmt="{v}%", always_include=(),
    pct_col=None, value_axis_title=None, pct_axis_title=None,
):
    """Builds one figure per available shift_pct value in df (via
    build_fig(subset_df_for_that_shift) -- typically a small wrapper around
    a px.bar/px.line call), then combines them into a single figure with
    buttons to toggle which one is visible.

    This exists because a Quarto-rendered report is static HTML/JS with no
    backend -- there's no way to re-run Python on a click, so "5%/10%/25%
    toggle" has to mean "pre-build all of them and let Plotly's own
    updatemenus show/hide traces client-side," not a real parameter
    callback. Every shift level's figure must produce the same number of
    traces in the same order (same category_orders/color_discrete_map
    every call) for the toggle to swap between them cleanly -- this raises
    a clear error if a shift level's trace count doesn't match, rather than
    silently mismatching what each button reveals.

    Only offers buttons for shift levels actually present in df -- if only
    5%/10% have a curated run so far, only those two buttons appear; a
    button for 25% appears automatically once Closer07/08/09 land, no code
    change needed here.

    always_include lets a value of shift_col (e.g. 0, the baseline scenario)
    be folded into every button's subset instead of becoming a button of its
    own -- for a chart like the trip-length distribution that wants the
    baseline curve shown alongside whichever shift level is selected, not a
    separate "0%" toggle option.

    pct_col, if given, names a second y-column already present in df (e.g.
    "pct_DY_VHD", each row's delta expressed as a percent of its own
    baseline) that lets a viewer judge a change's size relative to the
    baseline, not just its raw units. build_fig must then accept a second,
    optional `y_col` argument (defaulting to whichever column it hardcodes
    for the absolute case, e.g. `def _build(sub, y_col='delta_DY_VHD')`) so
    it can be called again with y_col=pct_col -- same grouping/category
    order, only the y-column differs, so the resulting traces line up 1:1
    with the absolute-mode traces by position.

    This adds a second, independent row of buttons ("Absolute" / "% Change")
    that restyles trace.y (and the y-axis title) for every trace at once,
    rather than toggling visibility -- so it composes cleanly with the
    shift-level toggle: switching shift level never resets the value-mode
    choice, and switching value mode never resets which shift level is
    showing, because the two button rows act on disjoint trace properties
    (visible vs. y).

    The y-axis range is fixed (via _fixed_range) to span every shift level
    at once, separately for Absolute and % Change mode, so neither button
    row rescales the axis when clicked -- only _fixed_range's own padding
    changes the range, never a click.
    """
    all_values = sorted(df[shift_col].unique())
    shift_levels = [v for v in all_values if v not in always_include]
    if not shift_levels:
        raise ValueError("No shift levels with data to build a toggle for.")
    if default_shift not in shift_levels:
        default_shift = shift_levels[0]

    per_shift_figs = {
        s: build_fig(df[df[shift_col].isin([*always_include, s])]) for s in shift_levels
    }
    n_traces = len(per_shift_figs[shift_levels[0]].data)
    for s, f in per_shift_figs.items():
        if len(f.data) != n_traces:
            raise ValueError(
                f"Shift level {s} produced {len(f.data)} trace(s), expected {n_traces} (from "
                f"shift level {shift_levels[0]}) -- category_orders/color_discrete_map must be "
                "identical across shift levels for the toggle to swap between them cleanly."
            )

    per_shift_pct_figs = None
    if pct_col is not None:
        per_shift_pct_figs = {
            s: build_fig(df[df[shift_col].isin([*always_include, s])], y_col=pct_col) for s in shift_levels
        }
        for s, f in per_shift_pct_figs.items():
            if len(f.data) != n_traces:
                raise ValueError(
                    f"Percent-mode figure for shift level {s} produced {len(f.data)} trace(s), "
                    f"expected {n_traces} -- build_fig(sub, y_col=pct_col) must produce the same "
                    "trace structure as build_fig(sub)."
                )

    combined = go.Figure()
    for s in shift_levels:
        for trace in per_shift_figs[s].data:
            trace.visible = s == default_shift
            combined.add_trace(trace)
    combined.layout = per_shift_figs[default_shift].layout

    # Fixed y-axis range spanning every shift level (not just default_shift)
    # so toggling between 5%/10%/25% restyles which bars are visible without
    # also rescaling the axis -- a rescale on every click makes it hard to
    # judge whether one shift level's effect is actually bigger than
    # another's at a glance.
    abs_range = _fixed_range(trace.y for f in per_shift_figs.values() for trace in f.data)
    if abs_range is not None:
        combined.update_layout(yaxis=dict(range=abs_range))

    buttons = []
    for i, s in enumerate(shift_levels):
        visible = [False] * (n_traces * len(shift_levels))
        for j in range(n_traces):
            visible[i * n_traces + j] = True
        buttons.append(dict(label=shift_label_fmt.format(v=s), method="update", args=[{"visible": visible}]))

    updatemenus = [
        dict(
            type="buttons", direction="right", buttons=buttons, showactive=True,
            x=1, xanchor="right", y=1.32, yanchor="bottom", pad=dict(r=5, t=5),
        )
    ]

    if per_shift_pct_figs is not None:
        abs_y = [list(per_shift_figs[s].data[j].y) for s in shift_levels for j in range(n_traces)]
        pct_y = [list(per_shift_pct_figs[s].data[j].y) for s in shift_levels for j in range(n_traces)]
        # Same fixed-range treatment as abs_range above, computed separately
        # since percent values live on a different scale than the raw units
        # -- each mode gets its own range, fixed across all shift levels.
        pct_range = _fixed_range(trace.y for f in per_shift_pct_figs.values() for trace in f.data)
        value_axis_title = value_axis_title or combined.layout.yaxis.title.text
        pct_axis_title = pct_axis_title or f"{value_axis_title} (%)"
        updatemenus.append(dict(
            type="buttons", direction="right", showactive=True,
            buttons=[
                dict(label="Absolute", method="update", args=[{"y": abs_y}, {"yaxis.title.text": value_axis_title, "yaxis.range": abs_range}]),
                dict(label="% Change", method="update", args=[{"y": pct_y}, {"yaxis.title.text": pct_axis_title, "yaxis.range": pct_range}]),
            ],
            x=0, xanchor="left", y=1.32, yanchor="bottom", pad=dict(r=5, t=5),
        ))

    combined.update_layout(updatemenus=updatemenus)
    return combined
