############################################################
# report.py – Generates a nicely formatted ASCII report of the
# currently displayed spur data.  The report is meant to be human-
# readable in any text editor and can be attached to e‑mails or
# pasted into tickets without losing alignment.
#
# WHAT'S INCLUDED
# ----------------
# • Header with generation timestamp, dashboard version, operator
#   (optional), and source CSV if available.
# • Overview of all active dashboard filters (axis‑swap state,
#   Z‑axis type, thresholds, frequency ranges, normalisation).
# • Basic statistics on the spur set (count, loudest spur, median).
# • A tab‑aligned table of every spur that meets the Z‑Min
#   threshold, sorted by descending level.
# • If a warnings list is supplied, it is appended at the end.
#
# NOTE: SFDR data is intentionally NOT included, per user request.
############################################################
from __future__ import annotations

import datetime as _dt
from typing import List, Optional
import numpy as np
import pandas as pd

__all__ = ["build_report"]


# ---------------------------------------------------------------------------
# Helper: format table with dynamic column widths
# ---------------------------------------------------------------------------

def _format_table(df: pd.DataFrame, col_order: List[str]) -> str:
    """Return an ASCII table string with auto column widths."""
    out_cols = col_order
    # Compute width per column (header vs. cell value length)
    widths = {}
    for col in out_cols:
        header_len = len(col)
        cell_len = df[col].astype(str).map(len).max() if not df.empty else 0
        widths[col] = max(header_len, cell_len)

    # Header line
    header = " | ".join(f"{col:<{widths[col]}}" for col in out_cols)
    sep    = "-+-".join("-" * widths[col] for col in out_cols)
    lines  = [header, sep]

    # Data rows
    for _, row in df.iterrows():
        line = " | ".join(f"{str(row[col]):<{widths[col]}}" for col in out_cols)
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_report(
    df: pd.DataFrame,
    has_iq: bool,
    REF_AMP: dict,
    opt_cols: List[str],
    config: dict,
    zmin: float,
    z_axis_type: str,
    norm_enable: bool,
    norm_target: float,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    swap_axes: bool,
    warnings: Optional[List[str]] = None,
) -> str:
    """Create a formatted TXT report string."""

    # -------------------------------------------------------------------
    # 1) Filter dataframe exactly as dashboard does
    # -------------------------------------------------------------------
    if swap_axes:
        dff = df[(df["usrp_ghz"].between(y_min, y_max)) & (df["rfsg_ghz"].between(x_min, x_max))].copy()
    else:
        dff = df[(df["rfsg_ghz"].between(x_min, x_max)) & (df["usrp_ghz"].between(y_min, y_max))].copy()

    if z_axis_type == "amp":
        if norm_enable and norm_target is not None:
            dff["amp"] += dff["rfsg_ghz"].map(lambda f: norm_target - REF_AMP.get(f, 0))
        dff = dff[dff["amp"] >= zmin]
        dff["zval"] = dff["amp"]
    else:  # IQ
        dff = dff[dff["IQ"] >= zmin]
        dff["zval"] = dff["IQ"]

    # Sort by loudest first
    dff = dff.sort_values("zval", ascending=False).reset_index(drop=True)

    # -------------------------------------------------------------------
    # 2) Build main table DataFrame
    # -------------------------------------------------------------------
    base_cols = ["rfsg_ghz", "usrp_ghz", "zval"]
    if has_iq and z_axis_type != "IQ":
        base_cols.append("IQ")  # show IQ even in amplitude mode if present

    for opt in opt_cols:
        if opt in dff.columns and not dff[opt].isna().all():
            base_cols.append(opt)

    tbl = dff[base_cols].copy()
    # Round for readability
    tbl["rfsg_ghz"] = tbl["rfsg_ghz"].round(6)
    tbl["usrp_ghz"] = tbl["usrp_ghz"].round(6)
    tbl["zval"]      = tbl["zval"].round(2 if z_axis_type == "amp" else 3)
    if "IQ" in tbl.columns:
        tbl["IQ"] = tbl["IQ"].round(3)
    for col in opt_cols:
        if col in tbl.columns:
            tbl[col] = tbl[col].round(3)

    # Rename columns for nicer header names
    col_ren = {
        "rfsg_ghz": "RFSG [GHz]",
        "usrp_ghz": "USRP [GHz]",
        "zval": "Power [dBFS]" if z_axis_type == "amp" else "IQ_VAL",
    }
    tbl.rename(columns=col_ren, inplace=True)

    # -------------------------------------------------------------------
    # 3) Statistics
    # -------------------------------------------------------------------
    stats_lines: List[str] = []
    if not tbl.empty:
        loudest = tbl.iloc[0]
        stats_lines.append(f"# Spur Count      : {len(tbl)}")
        stats_lines.append(
            f"# Loudest Spur    : {loudest[col_ren['zval']]:.2f} @ "
            f"RFSG={loudest['RFSG [GHz]']:.6f} GHz / USRP={loudest['USRP [GHz]']:.6f} GHz"
        )
        median_val = tbl[col_ren["zval"]].median()
        stats_lines.append(f"# Median Spur     : {median_val:.2f}")
    else:
        stats_lines.append("# Spur Count      : 0")

    # -------------------------------------------------------------------
    # 4) Header & filter block
    # -------------------------------------------------------------------
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_lines = [
        f"# File generated : {ts}",
        f"# Dashboard ver. : {config.get('version', 'n/a')}",
        "#",  # blank line
        "# Active Filters",  # section title
        f"#   Axis Swap        : {'ON' if swap_axes else 'OFF'}",
        f"#   Z-Axis Type      : {'Amplitude (dBFS)' if z_axis_type=='amp' else 'IQ'}",
        f"#   Z-Min Threshold  : {zmin}",
        f"#   RFSG Range [GHz] : {x_min} ... {x_max}",
        f"#   USRP Range [GHz] : {y_min} ... {y_max}",
        f"#   Normalization    : {'ON ('+str(norm_target)+' dBc)' if (norm_enable and z_axis_type=='amp') else 'OFF'}",
        "#",  # blank line
        "# Statistics",  # section title
        *stats_lines,
        "#",  # blank line before table
    ]

    report_parts = ["\n".join(header_lines)]

    # -------------------------------------------------------------------
    # 5) Table
    # -------------------------------------------------------------------
    report_parts.append(_format_table(tbl, list(tbl.columns)))

    # -------------------------------------------------------------------
    # 6) Warnings (optional)
    # -------------------------------------------------------------------
    if warnings:
        report_parts.append("\n# WARNINGS")
        report_parts.extend(f"# - {w}" for w in warnings)

    return "\n".join(report_parts) + "\n"