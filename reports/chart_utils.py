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

figure_with_shift_toggle's own toggle buttons went through two more
layouts after that: first a stack of rows below the plot (eating into a
chart's declared height, since Plotly margins are subtracted from the
figure's total pixel height, not added on top of it -- a tall reserved
margin.b left barely any of a chart's `height=` for the actual plot when
several toggle dimensions were present), then their current form: a
vertically-stacked column in the RIGHT margin instead, alongside the plot
rather than below it. margin.r grows to fit the column; margin.b is left
alone, so a chart's `height=` goes almost entirely to the plot itself.
This is also why figure_with_shift_toggle unconditionally repositions the
legend to the same top-left band SLIDE_LEGEND already gives slides -- the
right column would otherwise collide with Plotly Express's default
top-right legend placement on non-slide (summary.qmd) charts.
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
# sitting right at the plot's own top edge (y=1.0), below the title.
SLIDE_LEGEND = dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0)

# Title: pinned near the very top of the figure so it has a fixed, known
# position regardless of legend/margin -- font_size is left to each chart.
SLIDE_TITLE = dict(y=0.97, yanchor="top")

# Top margin only has to fit a two-line title plus the legend band below it
# now that toggle buttons (figure_with_shift_toggle) live below the plot
# instead of above it.
SLIDE_MARGIN = dict(t=90)

# Full-bleed width for a single, one-chart-per-slide figure on this deck's
# 1280px-wide RevealJS canvas (1280 minus reasonable left/right slide
# padding) -- Plotly figures have a fixed pixel width, not a responsive
# one, so without this every chart defaulted to Plotly Express's own ~700px
# width and sat with large empty margins on either side. A chart placed in
# a two-column ::: {.column width="50%"} ::: layout must override this back
# down to roughly half (see e.g. slides.qmd's paired VHT/trip-length and
# city charts, each passing their own width=560) -- the template default
# only fits a full-width slide.
SLIDE_CHART_WIDTH = 1150


def use_slide_chart_defaults():
    """Call once, in a slides.qmd's setup cell, after importing
    plotly.express -- registers a Plotly template giving every
    subsequently-created figure in this document a top-left legend, a
    pinned title position, reserved top margin, and a full slide-width
    default size, so title and legend don't compete for space and a chart
    isn't left stranded at Plotly's own default ~700px width on a 1280px
    slide. A chart can still override any of this further (e.g.
    legend=dict(y=1.15) for an extra-tall title, or width=560 for a
    two-column layout) or turn the legend off entirely (showlegend=False);
    this only sets what happens if it doesn't -- an explicit per-chart
    value always wins over the template default."""
    pio.templates["wfrc_slide_legend"] = go.layout.Template(
        layout=go.Layout(legend=SLIDE_LEGEND, title=SLIDE_TITLE, margin=SLIDE_MARGIN, width=SLIDE_CHART_WIDTH)
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
_NO_GROUP = "__no_group__"

# Toggle-button styling: the currently-selected option gets a dark navy
# background + white text; every other option in its row gets a light-teal
# background + navy text. Plotly's own updatemenus have no per-button
# active-state styling (bgcolor/font are set on the whole updatemenu, not
# on individual buttons within it) -- so each "button" the user sees is
# actually its own single-button updatemenu, positioned side by side to
# look like one row, restyled via relayout on click. WFRC brand colors
# (see CLAUDE.md): navy #1B3A5C, light teal #E8F4F8.
_ACTIVE_BG, _ACTIVE_FG = "#1B3A5C", "#FFFFFF"
_INACTIVE_BG, _INACTIVE_FG = "#E8F4F8", "#1B3A5C"


def _button_style(active: bool) -> dict:
    return dict(
        bgcolor=_ACTIVE_BG if active else _INACTIVE_BG,
        font=dict(color=_ACTIVE_FG if active else _INACTIVE_FG, size=11),
        bordercolor="#1B3A5C", borderwidth=1,
    )


# Plotly sizes an updatemenu button to its own label text plus `pad`, with
# no direct "button width" property -- so to make every toggle button the
# same width (rather than each one shrink-wrapped to its own label), we pad
# the SHORTER labels extra on both sides to approximate the width of the
# longest label used anywhere in this toggle system ("Medium District",
# one of the group_col values) at the button font size. This is an
# approximation (proportional-font glyph widths aren't uniform per
# character), not exact pixel matching, but visually evens out button
# widths across a page whose buttons otherwise range from "5%" to "Medium
# District".
_BUTTON_REF_LABEL = "Medium District"
_BUTTON_CHAR_PX = 6.5
_BUTTON_BASE_PAD = 6


def _button_pad(label: str) -> dict:
    extra = max(0.0, (len(_BUTTON_REF_LABEL) - len(label)) * _BUTTON_CHAR_PX / 2)
    side = _BUTTON_BASE_PAD + extra
    return dict(l=side, r=side, t=4, b=4)


def _row_highlight(indices: list, active_pos: int) -> dict:
    """Relayout dict recoloring every sibling single-button menu in a row
    (indices, their position in the figure's combined updatemenus list) so
    the one at active_pos looks selected and the rest don't."""
    out = {}
    for pos, idx in enumerate(indices):
        style = _button_style(pos == active_pos)
        out[f"updatemenus[{idx}].bgcolor"] = style["bgcolor"]
        out[f"updatemenus[{idx}].font.color"] = style["font"]["color"]
    return out


# Right-hand toggle column layout: one vertically-stacked group of buttons
# per toggle dimension (shift/period/group/pct), all at the same x, top to
# bottom in the order the groups are built -- see _col_menus/COL_X below.
COL_X = 1.04
COL_TOP_Y = 0.97
COL_BUTTON_DY = 0.12
COL_GROUP_GAP = 0.07


def _col_menus(labels: list, indices: list, active_pos: int, y_positions: list, args_fn, x: float = COL_X) -> list:
    """Builds one vertically-stacked group of individually-stylable toggle
    "buttons" as sibling single-button updatemenus, all at the same x (just
    right of the plot, in the reserved right margin) and one y per
    y_positions entry (already laid out top-to-bottom by the caller).
    indices are these menus' own final positions in the figure's combined
    updatemenus list (known ahead of time since groups are appended in
    order) -- needed so each button's click handler can recolor its whole
    group via `updatemenus[i].bgcolor` relayout paths. args_fn(pos) returns
    this button's own "update"-method args list (trace restyle / layout
    changes) BEFORE the group-highlight relayout is appended -- this
    function appends it."""
    menus = []
    for pos, (label, idx, y) in enumerate(zip(labels, indices, y_positions)):
        args = list(args_fn(pos))
        if len(args) < 2:
            args = args + [{}]
        args[1] = {**args[1], **_row_highlight(indices, pos)}
        style = _button_style(pos == active_pos)
        menus.append(dict(
            type="buttons", direction="right", showactive=False,
            x=x, xanchor="left",
            y=y, yanchor="middle", pad=_button_pad(label),
            bgcolor=style["bgcolor"], font=style["font"],
            bordercolor=style["bordercolor"], borderwidth=style["borderwidth"],
            buttons=[dict(label=label, method="update", args=args)],
        ))
    return menus


def figure_with_shift_toggle(
    df, build_fig, shift_col="shift_pct", default_shift=10, shift_label_fmt="{v}%", always_include=(),
    pct_col=None, value_axis_title=None, pct_axis_title=None,
    period_col=None, default_period=None, period_order=None,
    group_col=None, default_group=None, group_order=None, group_label_fmt="{v}",
    global_shift=False, numeric_x=False,
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
    "Off-Peak"/"Daily") that adds another, independent row of buttons
    filtering df to one period at a time. group_col works exactly the same
    way for a second such dimension (e.g. "geography_label", values "City
    Area"/"Medium District"/"Workshop Area") -- both are VISIBILITY-based,
    the same mechanism as the shift-level toggle itself (build_fig produces
    a genuinely different set of traces per period/group, rather than just
    a different y-column), necessary because period/group change what rows
    feed the aggregation, not just which column of an already-aggregated
    row to plot. df is filtered on shift_col (+ period_col, + group_col,
    whichever are given) before build_fig is called for every combination.
    period_order/group_order fix each row's button order (e.g. ["Peak",
    "Off-Peak", "Daily"]) instead of relying on alphabetical sort.

    Because shift-level, period, and group are all visibility-based, they
    can't be made fully independent without custom client-side JS tracking
    which button was clicked last (static Plotly updatemenus can't read
    each other's current state) -- clicking any one of these rows' buttons
    resets the OTHER visibility-based rows to their own default. This is a
    deliberate, documented simplification, not an oversight: full N-way
    independence would need a real client-side callback. The Absolute/%
    Change row (pct_col), being y-swap based rather than visibility-based,
    remains fully independent of shift level, period, and group regardless.

    Every toggle dimension renders as its own vertically-stacked group of
    buttons in a column to the RIGHT of the plot (not below it, and not
    alongside the title/legend) -- shift level nearest the top, then
    period, then group, then Absolute/% Change, top to bottom -- each
    group's currently-selected button shown with a dark navy background
    and white text (see _col_menus/_button_style) so the active choice is
    unambiguous at a glance, since Plotly's own updatemenus have no
    built-in active-button highlighting for a "buttons"-type menu. This
    column lives inside the plot's own y-range (paper y 0..1), not in a
    reserved margin, so a chart's declared `height=` isn't eaten by toggle
    space the way a below-the-plot row stack used to; only margin.r grows,
    sized to fit the widest button label actually rendered.

    numeric_x=True rounds hover text on the x-axis too (3 significant
    figures, same as y), for a chart whose x is a continuous value rather
    than a category -- see _round_hover above.

    global_shift=True suppresses this chart's OWN shift-level button row
    entirely (no per-chart 5%/10%/25% buttons) and instead stashes what
    that row would have done into `combined.layout.meta["wfrcShiftLevels"]`
    -- a plain list of {label, visible, relayout} dicts, one per shift
    level, with exactly the trace-visibility array and cross-row highlight
    reset a local button's "args" would have carried. This is for
    slides.qmd's deck-wide shift-level control (see
    reports/global_shift_toggle.html): one fixed on-screen control
    restyles every chart in the whole deck by reading each chart's own
    `layout.meta.wfrcShiftLevels` and calling `Plotly.update` with the
    matching entry, rather than each chart carrying its own buttons.
    Period/group/pct rows, if present, are unaffected and still render
    per-chart -- only the shift-level row is globalized, since it's the one
    dimension every chart on that deck shares. summary.qmd's charts don't
    use this (global_shift defaults to False), so they keep their own
    per-chart shift buttons as before.
    """
    have_period = period_col is not None
    have_group = group_col is not None
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

    if have_group:
        groups = group_order or sorted(df[group_col].unique())
        if default_group is None or default_group not in groups:
            default_group = groups[0]
    else:
        groups = [_NO_GROUP]
        default_group = _NO_GROUP

    def _subset(s, p, g):
        mask = df[shift_col].isin([*always_include, s])
        if have_period:
            mask &= df[period_col] == p
        if have_group:
            mask &= df[group_col] == g
        return df[mask]

    cells = [(s, p, g) for s in shift_levels for p in periods for g in groups]
    per_cell_figs = {key: build_fig(_subset(*key)) for key in cells}
    n_traces = len(per_cell_figs[cells[0]].data)
    for key, f in per_cell_figs.items():
        if len(f.data) != n_traces:
            raise ValueError(
                f"Shift/period/group combination {key!r} produced {len(f.data)} trace(s), "
                f"expected {n_traces} (from {cells[0]!r}) -- category_orders/"
                "color_discrete_map must be identical across every combination for the "
                "toggle to swap between them cleanly."
            )

    per_cell_pct_figs = None
    if pct_col is not None:
        per_cell_pct_figs = {key: build_fig(_subset(*key), y_col=pct_col) for key in cells}
        for key, f in per_cell_pct_figs.items():
            if len(f.data) != n_traces:
                raise ValueError(
                    f"Percent-mode figure for combination {key!r} produced {len(f.data)} "
                    f"trace(s), expected {n_traces} -- build_fig(sub, y_col=pct_col) must "
                    "produce the same trace structure as build_fig(sub)."
                )

    # No per-bar value labels -- tried, but they cluttered every chart with
    # a toggle-heavy layout; hover (below) carries the same rounded value
    # on demand instead. is_bar_chart still distinguishes bar charts from
    # line/scatter charts for other purposes below.
    is_bar_chart = bool(per_cell_figs[cells[0]].data) and per_cell_figs[cells[0]].data[0].type == "bar"

    # Plotly Express's own auto-generated hovertemplate leaves %{x}/%{y}
    # unformatted, so hovering shows the raw float (often a dozen decimal
    # digits from an upstream division) regardless of the value's actual
    # magnitude -- unlike the fixed-decimal texttemplate above (reasonable
    # for a single known unit), hover has to cover every metric this
    # module ever plots, from sub-1 trip-length deltas to five-digit VMT
    # totals, so a single fixed decimal count is either noisy or rounds
    # small values to nothing. Round to 3 significant digits instead (d3
    # format's "r" type) -- scales with magnitude automatically. Only %{y}
    # is touched by default (a bar/line chart's x is a category, not a
    # number); pass numeric_x=True for a chart whose x-axis is ALSO a
    # continuous value (e.g. the VMT-vs-VHT/HH scatter) to round that too
    # -- deliberately explicit rather than guessed from trace type, since
    # trip-length-distribution's px.line is also a "scatter"-type trace
    # but its x is a categorical bin label, not a number.
    def _round_hover(trace):
        if not trace.hovertemplate:
            return
        ht = trace.hovertemplate.replace("%{y}", "%{y:+,.3r}")
        if numeric_x:
            ht = ht.replace("%{x}", "%{x:+,.3r}")
        trace.hovertemplate = ht

    for f in per_cell_figs.values():
        for trace in f.data:
            _round_hover(trace)
    if per_cell_pct_figs is not None:
        for f in per_cell_pct_figs.values():
            for trace in f.data:
                _round_hover(trace)

    default_cell = (default_shift, default_period, default_group)
    combined = go.Figure()
    for key in cells:
        for trace in per_cell_figs[key].data:
            trace.visible = key == default_cell
            combined.add_trace(trace)
    combined.layout = per_cell_figs[default_cell].layout

    # Fixed y-axis range spanning every combination at once (not just the
    # default cell) so toggling restyles which bars are visible without
    # also rescaling the axis -- a rescale on every click makes it hard to
    # judge whether one selection's effect is actually bigger than
    # another's at a glance.
    abs_range = _fixed_range(trace.y for f in per_cell_figs.values() for trace in f.data)
    if abs_range is not None:
        combined.update_layout(yaxis=dict(range=abs_range))

    def _visible_for(fixed_shift=None, fixed_period=None, fixed_group=None):
        visible = []
        for s, p, g in cells:
            match = (
                (fixed_shift is None or s == fixed_shift)
                and (fixed_period is None or p == fixed_period)
                and (fixed_group is None or g == fixed_group)
            )
            visible.extend([match] * n_traces)
        return visible

    # Row layout: figure out every row's button count up front so each
    # row's sibling menus know their own final index in the combined
    # updatemenus list before any button's click args are built (rows are
    # appended in this same order, so indices are contiguous per row).
    shift_labels = [shift_label_fmt.format(v=s) for s in shift_levels]
    period_labels = [str(p) for p in periods] if have_period else []
    group_labels = [group_label_fmt.format(v=g) for g in groups] if have_group else []
    pct_labels = ["Absolute", "% Change"] if per_cell_pct_figs is not None else []

    # global_shift=True skips reserving a row/index block for the shift
    # level entirely -- no local shift buttons are built, so nothing should
    # claim updatemenus indices or a row_y slot for it.
    shift_indices = []
    next_idx = 0
    if not global_shift:
        shift_indices = list(range(0, len(shift_labels)))
        next_idx = len(shift_indices)
    period_indices = []
    if have_period:
        period_indices = list(range(next_idx, next_idx + len(period_labels)))
        next_idx += len(period_indices)
    group_indices = []
    if have_group:
        group_indices = list(range(next_idx, next_idx + len(group_labels)))
        next_idx += len(group_indices)
    pct_indices = []
    if per_cell_pct_figs is not None:
        pct_indices = list(range(next_idx, next_idx + len(pct_labels)))
        next_idx += len(pct_indices)

    n_rows = int(not global_shift) + int(have_period) + int(have_group) + int(per_cell_pct_figs is not None)
    # Lay out each present toggle group as its own vertically-stacked block
    # in the right-hand column, top to bottom in build order -- a cursor
    # walks down from COL_TOP_Y, each group claiming one y position per
    # button plus a gap before the next group. This lives entirely within
    # the plot's own 0..1 paper-y range (never needs to steal from the
    # figure's overall height the way a below-the-plot row stack used to),
    # so a chart's declared `height=` goes almost entirely to the plot
    # itself instead of being eaten by reserved toggle space.
    _cursor = COL_TOP_Y

    def _alloc_col(n):
        nonlocal _cursor
        ys = [_cursor - i * COL_BUTTON_DY for i in range(n)]
        _cursor -= n * COL_BUTTON_DY + COL_GROUP_GAP
        return ys

    row_y = {}
    if not global_shift:
        row_y["shift"] = _alloc_col(len(shift_labels))
    if have_period:
        row_y["period"] = _alloc_col(len(period_labels))
    if have_group:
        row_y["group"] = _alloc_col(len(group_labels))
    if per_cell_pct_figs is not None:
        row_y["pct"] = _alloc_col(len(pct_labels))

    # Clicking any one visibility-based row's button resets the OTHER
    # visibility-based rows to their own default (see the period_col/
    # group_col docstring paragraph above) -- so each row's own click
    # handler also has to visually reset every other such row back to its
    # default button, not just re-highlight itself, or the rows could show
    # a selection that no longer matches what's actually visible. There's
    # nothing to reset for shift when global_shift=True -- no local shift
    # row exists on this chart, so it's skipped rather than referencing
    # indices that were never assigned.
    def _other_row_reset(exclude):
        out = {}
        if have_period and exclude != "period":
            out.update(_row_highlight(period_indices, periods.index(default_period)))
        if have_group and exclude != "group":
            out.update(_row_highlight(group_indices, groups.index(default_group)))
        if not global_shift and exclude != "shift":
            out.update(_row_highlight(shift_indices, shift_levels.index(default_shift)))
        return out

    updatemenus = []
    if global_shift:
        # Deck-wide shift toggle (slides.qmd): stash each shift level's
        # trace-visibility array and cross-row reset into layout.meta
        # instead of building visible buttons -- see reports/
        # global_shift_toggle.html, which reads this from every chart on
        # the page and drives them all from one fixed on-screen control.
        combined.update_layout(meta={
            "wfrcShiftLevels": [
                {
                    "label": shift_label_fmt.format(v=s),
                    "visible": _visible_for(fixed_shift=s, fixed_period=default_period, fixed_group=default_group),
                    "relayout": _other_row_reset("shift"),
                }
                for s in shift_levels
            ],
        })
    else:
        def _shift_args(pos):
            s = shift_levels[pos]
            return [
                {"visible": _visible_for(fixed_shift=s, fixed_period=default_period, fixed_group=default_group)},
                _other_row_reset("shift"),
            ]
        updatemenus = _col_menus(shift_labels, shift_indices, shift_levels.index(default_shift), row_y["shift"], _shift_args)

    if have_period:
        def _period_args(pos):
            p = periods[pos]
            return [
                {"visible": _visible_for(fixed_shift=default_shift, fixed_period=p, fixed_group=default_group)},
                _other_row_reset("period"),
            ]
        updatemenus += _col_menus(period_labels, period_indices, periods.index(default_period), row_y["period"], _period_args)

    if have_group:
        def _group_args(pos):
            g = groups[pos]
            return [
                {"visible": _visible_for(fixed_shift=default_shift, fixed_period=default_period, fixed_group=g)},
                _other_row_reset("group"),
            ]
        updatemenus += _col_menus(group_labels, group_indices, groups.index(default_group), row_y["group"], _group_args)

    if per_cell_pct_figs is not None:
        abs_y = [list(per_cell_figs[key].data[j].y) for key in cells for j in range(n_traces)]
        pct_y = [list(per_cell_pct_figs[key].data[j].y) for key in cells for j in range(n_traces)]
        pct_range = _fixed_range(trace.y for f in per_cell_pct_figs.values() for trace in f.data)
        value_axis_title = value_axis_title or combined.layout.yaxis.title.text
        pct_axis_title = pct_axis_title or f"{value_axis_title} (%)"

        def _pct_args(pos):
            if pos == 0:
                layout_extra = {
                    "yaxis.title.text": value_axis_title, "yaxis.range": abs_range,
                    "yaxis.tickformat": ".1f", "yaxis.ticksuffix": "",
                }
                return [{"y": abs_y}, layout_extra]
            layout_extra = {
                "yaxis.title.text": pct_axis_title, "yaxis.range": pct_range,
                "yaxis.tickformat": ".1f", "yaxis.ticksuffix": "%",
            }
            return [{"y": pct_y}, layout_extra]
        updatemenus += _col_menus(pct_labels, pct_indices, 0, row_y["pct"], _pct_args)

    # Legend moves to a horizontal band above the plot's own top-left edge
    # (same position use_slide_chart_defaults() gives slides) so it never
    # competes with the new right-hand toggle column for space -- harmless
    # if this chart has no visible legend.
    combined.update_layout(legend=SLIDE_LEGEND)

    # Right margin sized to fit the widest button label actually rendered,
    # so the toggle column has room without being clipped -- charts still
    # set their own top margin/height afterward (e.g. `fig.update_layout
    # (margin=dict(t=80))`), which merges with, rather than replaces, this
    # right-margin value. No toggle groups at all (n_rows == 0) leaves
    # margin.r untouched, since there's no column to reserve space for.
    if n_rows > 0:
        all_labels = shift_labels + period_labels + group_labels + pct_labels
        max_label_len = max(len(label) for label in all_labels)
        margin_r = min(220, max(110, 34 + 8 * max_label_len))
        combined.update_layout(margin=dict(r=margin_r))
    combined.update_layout(updatemenus=updatemenus)
    return combined


# ---------------------------------------------------------------------------
# Table toggle: pandas Styler tables are plain HTML, not Plotly figures, so
# figure_with_shift_toggle's client-side updatemenus trick doesn't apply --
# this is the equivalent for "all tables get an Absolute/% Change toggle."
# ---------------------------------------------------------------------------

_TABLE_TOGGLE_SCRIPT = """
<script>
function wfrcToggleTable(tableId, mode) {
  var abs = document.getElementById(tableId + '_abs');
  var pct = document.getElementById(tableId + '_pct');
  var bAbs = document.getElementById(tableId + '_btn_abs');
  var bPct = document.getElementById(tableId + '_btn_pct');
  abs.style.display = (mode === 'abs') ? '' : 'none';
  pct.style.display = (mode === 'pct') ? '' : 'none';
  bAbs.style.background = (mode === 'abs') ? '#1B3A5C' : '#E8F4F8';
  bAbs.style.color = (mode === 'abs') ? '#FFFFFF' : '#1B3A5C';
  bPct.style.background = (mode === 'pct') ? '#1B3A5C' : '#E8F4F8';
  bPct.style.color = (mode === 'pct') ? '#FFFFFF' : '#1B3A5C';
}
</script>
"""

_TABLE_BUTTON_CSS = (
    "display:inline-block;padding:4px 14px;margin:0 6px 10px 0;border:1px solid #1B3A5C;"
    "border-radius:4px;cursor:pointer;font-size:0.85em;font-family:inherit;user-select:none;"
)


def styled_table_with_toggle(table_id: str, abs_styler, pct_styler, default: str = "abs") -> str:
    """Wraps two pandas Styler objects -- one with delta columns shown in
    their native units, one with the same columns shown as a percent of
    baseline -- in a small Absolute/% Change button pair plus two divs,
    shown/hidden via inline JS. Renders under the SAME toggle color scheme
    as figure_with_shift_toggle's chart buttons (dark navy = selected,
    light teal = not) for visual consistency across the page. Returns an
    HTML string; render it with `display(HTML(...))`, not `Markdown(...)`
    (Styler's own <style> block needs to reach the page unescaped).

    table_id must be unique on the page (becomes the id= prefix for both
    table divs and both buttons) -- reused across scenarios/tables would
    make every same-named toggle move together instead of independently.
    """
    abs_display = "" if default == "abs" else "display:none;"
    pct_display = "" if default == "pct" else "display:none;"
    abs_bg, abs_fg = (_ACTIVE_BG, _ACTIVE_FG) if default == "abs" else (_INACTIVE_BG, _INACTIVE_FG)
    pct_bg, pct_fg = (_ACTIVE_BG, _ACTIVE_FG) if default == "pct" else (_INACTIVE_BG, _INACTIVE_FG)
    return f"""
{_TABLE_TOGGLE_SCRIPT}
<div>
  <span id="{table_id}_btn_abs" style="{_TABLE_BUTTON_CSS}background:{abs_bg};color:{abs_fg};"
        onclick="wfrcToggleTable('{table_id}', 'abs')">Absolute</span>
  <span id="{table_id}_btn_pct" style="{_TABLE_BUTTON_CSS}background:{pct_bg};color:{pct_fg};"
        onclick="wfrcToggleTable('{table_id}', 'pct')">% Change</span>
</div>
<div id="{table_id}_abs" style="{abs_display}">{abs_styler.to_html()}</div>
<div id="{table_id}_pct" style="{pct_display}">{pct_styler.to_html()}</div>
"""
