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

The top margin stacks three tiers, top to bottom: title (SLIDE_TITLE,
pinned near the absolute top of the figure via container-relative y, so
its position doesn't shift with margin/plot-height changes) -> toggle
buttons, where present (figure_with_shift_toggle's updatemenus, plot-area-
relative y) -> legend (SLIDE_LEGEND, also plot-area-relative, closest tier
to the plot). Toggle buttons used to float above the legend, even above
the title on some charts -- moved below the title on purpose, since
buttons floating above everything else read as disconnected from the
chart they control. SLIDE_MARGIN's t is sized for exactly this three-tier
stack; if any tier's y moves, re-check the other two don't collide (see
the pixel-math approach in the session that introduced this ordering).
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
# the tier closest to the plot -- sits right at the plot's own top edge
# (y=1.0), below both the title and (where present) the toggle buttons.
SLIDE_LEGEND = dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0)

# Title: pinned near the very top of the figure so it has a fixed, known
# position regardless of legend/margin -- font_size is left to each chart.
SLIDE_TITLE = dict(y=0.97, yanchor="top")

# Enough reserved top margin for a two-line title (text + <br><sup>subtitle),
# the toggle-button row below it, and the legend band below that, without
# any tier being clipped or cramped against another.
SLIDE_MARGIN = dict(t=140)


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


_NO_PERIOD = "__no_period__"


def figure_with_shift_toggle(
    df, build_fig, shift_col="shift_pct", default_shift=10, shift_label_fmt="{v}%", always_include=(),
    pct_col=None, value_axis_title=None, pct_axis_title=None,
    period_col=None, default_period=None, period_order=None,
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

    period_col, if given, names a column (e.g. "period", values like "Peak"/
    "Off-Peak") that adds a THIRD, independent row of buttons filtering df
    to one period at a time -- df is filtered to period_col == p (in
    addition to the shift_col/always_include filtering) before build_fig is
    called for every (shift, period) combination. Unlike pct_col, this is
    VISIBILITY-based, the same mechanism as the shift-level toggle itself
    (build_fig produces a genuinely different set of traces per period,
    rather than just a different y-column) -- necessary because period
    changes what rows feed the aggregation (e.g. sum of AM+PM SEGID columns
    vs. MD+EV), not just which column of an already-aggregated row to plot.

    Because both shift-level and period are visibility-based, they can't be
    made fully independent without custom client-side JS tracking which
    button was clicked last (static Plotly updatemenus can't read each
    other's current state) -- clicking a period button resets the shift
    level to default_shift, and clicking a shift button resets the period to
    default_period. This is a deliberate, documented simplification, not an
    oversight: full 3-way independence (shift x period x value-mode) would
    need a real client-side callback. The Absolute/% Change row (pct_col),
    being y-swap based rather than visibility-based, remains fully
    independent of both shift level and period regardless.
    """
    have_period = period_col is not None
    all_values = sorted(df[shift_col].unique())
    shift_levels = [v for v in all_values if v not in always_include]
    if not shift_levels:
        raise ValueError("No shift levels with data to build a toggle for.")
    if default_shift not in shift_levels:
        default_shift = shift_levels[0]

    if have_period:
        periods = period_order or sorted(df[period_col].unique())
        if default_period is None or default_period not in periods:
            default_period = periods[0]
    else:
        periods = [_NO_PERIOD]
        default_period = _NO_PERIOD

    def _subset(s, p):
        mask = df[shift_col].isin([*always_include, s])
        if have_period:
            mask &= df[period_col] == p
        return df[mask]

    per_cell_figs = {(s, p): build_fig(_subset(s, p)) for s in shift_levels for p in periods}
    n_traces = len(per_cell_figs[(shift_levels[0], periods[0])].data)
    for (s, p), f in per_cell_figs.items():
        if len(f.data) != n_traces:
            raise ValueError(
                f"Shift level {s}, period {p!r} produced {len(f.data)} trace(s), expected "
                f"{n_traces} (from shift level {shift_levels[0]}, period {periods[0]!r}) -- "
                "category_orders/color_discrete_map must be identical across every shift "
                "level/period combination for the toggle to swap between them cleanly."
            )

    per_cell_pct_figs = None
    if pct_col is not None:
        per_cell_pct_figs = {
            (s, p): build_fig(_subset(s, p), y_col=pct_col) for s in shift_levels for p in periods
        }
        for (s, p), f in per_cell_pct_figs.items():
            if len(f.data) != n_traces:
                raise ValueError(
                    f"Percent-mode figure for shift level {s}, period {p!r} produced "
                    f"{len(f.data)} trace(s), expected {n_traces} -- build_fig(sub, "
                    "y_col=pct_col) must produce the same trace structure as build_fig(sub)."
                )

    combined = go.Figure()
    for s in shift_levels:
        for p in periods:
            for trace in per_cell_figs[(s, p)].data:
                trace.visible = s == default_shift and p == default_period
                combined.add_trace(trace)
    combined.layout = per_cell_figs[(default_shift, default_period)].layout

    # Fixed y-axis range spanning every shift level and period at once (not
    # just the default cell) so toggling restyles which bars are visible
    # without also rescaling the axis -- a rescale on every click makes it
    # hard to judge whether one selection's effect is actually bigger than
    # another's at a glance.
    abs_range = _fixed_range(trace.y for f in per_cell_figs.values() for trace in f.data)
    if abs_range is not None:
        combined.update_layout(yaxis=dict(range=abs_range))

    def _visible_for(fixed_shift=None, fixed_period=None):
        visible = []
        for s in shift_levels:
            for p in periods:
                match = (fixed_shift is None or s == fixed_shift) and (fixed_period is None or p == fixed_period)
                visible.extend([match] * n_traces)
        return visible

    shift_buttons = [
        dict(
            label=shift_label_fmt.format(v=s), method="update",
            args=[{"visible": _visible_for(fixed_shift=s, fixed_period=default_period)}],
        )
        for s in shift_levels
    ]
    updatemenus = [
        dict(
            type="buttons", direction="right", buttons=shift_buttons, showactive=True,
            x=1, xanchor="right", y=1.15, yanchor="bottom", pad=dict(r=5, t=5),
        )
    ]

    if have_period:
        period_buttons = [
            dict(
                label=str(p), method="update",
                args=[{"visible": _visible_for(fixed_shift=default_shift, fixed_period=p)}],
            )
            for p in periods
        ]
        updatemenus.append(dict(
            type="buttons", direction="right", buttons=period_buttons, showactive=True,
            x=1, xanchor="right", y=1.0, yanchor="bottom", pad=dict(r=5, t=5),
        ))

    if per_cell_pct_figs is not None:
        abs_y = [list(per_cell_figs[(s, p)].data[j].y) for s in shift_levels for p in periods for j in range(n_traces)]
        pct_y = [list(per_cell_pct_figs[(s, p)].data[j].y) for s in shift_levels for p in periods for j in range(n_traces)]
        # Same fixed-range treatment as abs_range above, computed separately
        # since percent values live on a different scale than the raw units
        # -- each mode gets its own range, fixed across every shift/period.
        pct_range = _fixed_range(trace.y for f in per_cell_pct_figs.values() for trace in f.data)
        value_axis_title = value_axis_title or combined.layout.yaxis.title.text
        pct_axis_title = pct_axis_title or f"{value_axis_title} (%)"
        updatemenus.append(dict(
            type="buttons", direction="right", showactive=True,
            buttons=[
                dict(label="Absolute", method="update", args=[{"y": abs_y}, {"yaxis.title.text": value_axis_title, "yaxis.range": abs_range}]),
                dict(label="% Change", method="update", args=[{"y": pct_y}, {"yaxis.title.text": pct_axis_title, "yaxis.range": pct_range}]),
            ],
            x=0, xanchor="left", y=1.15, yanchor="bottom", pad=dict(r=5, t=5),
        ))

    combined.update_layout(updatemenus=updatemenus)
    return combined
