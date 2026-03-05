import numpy as np
import pandas as pd
import plotly.graph_objects as go
import time
from dash import Input, Output, State, callback_context, ctx, html
from dash import no_update
from settings import CONFIG, OPT
from report import build_report
from layout import get_axes_config  # ← Import axis‐config helper

# Hilfsfunktion zum Formatieren auf signifikante Stellen (z. B. 5)
def format_sig(x, sig=5):
    """Formatiert eine Zahl mit sig signifikanten Stellen als String"""
    if x == 0:
        return "0"
    from math import log10, floor
    return f"{x:.{sig - int(floor(log10(abs(x)))) - 1}f}"

def register_callbacks(app, df, has_iq, REF_AMP, REF_USRP,
                       USRP_CENTERS, USRP_BW_GHZ,
                       RFSG_MIN_AUTO, RFSG_MAX_AUTO,
                       USRP_MIN_AUTO, USRP_MAX_AUTO,
                       warnings):
    def clamp(default, relayout, key):
        return relayout.get(key, default) if relayout and key in relayout else default

    @app.callback(
        Output("zmin", "value"),
        Output("zmax", "value"),
        Input("zaxis-type", "value"),
    )
    def reset_z_range(z_type: str):
        if z_type == "IQ":
            return CONFIG["zmin_iq"], CONFIG["zmax_iq"]
        return CONFIG["zmin_amp"], CONFIG["zmax_amp"]



    # -----------------------------------------------------------------------
    # INTENSITY-PLOT (ohne Sweep-Logik – nutzt clickData vom Spectrum-Plot)
    # -----------------------------------------------------------------------
    @app.callback(
        Output("intensity-plot", "figure"),
        Output("usrp-xrange", "data"),
        Output("binning-status", "children"),
        Input("zmin", "value"), Input("zmax", "value"),
        Input("x_min", "value"), Input("x_max", "value"),
        Input("y_min", "value"), Input("y_max", "value"),
        Input("norm-enable", "value"), Input("norm-target", "value"),
        Input("show-bands", "value"),
        Input("show-usrp-band", "value"), Input("usrp-bw", "value"),
        Input("zaxis-type", "value"),
        Input("intensity-plot", "relayoutData"),
        State("spectrum-plot", "clickData"),
        Input("swap-axes", "value"),
        Input("detailed-mode", "value"),
    )
    def update_intensity_plot(
        zmin, zmax, x_min, x_max, y_min, y_max,
        norm_enable, norm_target,
        show_bands, show_usrp_band, usrp_bw_mhz,
        z_type, relayout, click_data,
        swap_axes, detailed_mode,
    ):
        axes = get_axes_config("intensity", swap_axes=swap_axes)
        x_key, y_key = axes["x_key"], axes["y_key"]
        x_lab, y_lab = axes["x_label"], axes["y_label"]

        # ------------------------- 1) ClickData (optional)
        click_x, click_y = None, None
        if click_data and "points" in click_data:
            pt = click_data["points"][0]
            click_x = pt.get("x")
            click_y = pt.get("y")

        # ------------------------- 2) Bereichs-Filterung
        if click_x is not None and click_y is not None:
            dff = df[
                np.isclose(df["rfsg_ghz"], click_x, rtol=1e-6) &
                np.isclose(df["usrp_ghz"], click_y, rtol=1e-6)
            ].copy()
        else:
            dff = df[
                (df["rfsg_ghz"] >= x_min) & (df["rfsg_ghz"] <= x_max) &
                (df["usrp_ghz"] >= y_min) & (df["usrp_ghz"] <= y_max)
            ].copy()

        # ------------------------- 3) Z-Wert berechnen
        if z_type == "IQ" and has_iq and "IQ" in dff.columns:
            thr = zmin if zmin is not None else CONFIG["zmin_iq"]
            dff = dff[dff["IQ"] >= thr]
            dff["zval"] = dff["IQ"]
            z_title = "IQ"
            cmin = zmin if zmin is not None else CONFIG["zmin_iq"]
            cmax = zmax if zmax is not None else CONFIG["zmax_iq"]
        else:
            thr = zmin if zmin is not None else CONFIG["zmin_amp"]
            dff = dff[dff["amp"] >= thr]
            dff["zval"] = dff["amp"]

            if norm_enable and norm_target is not None and not dff.empty:
                norm_count = CONFIG.get("norm_peak_count", 100)
                sorted_vals = dff["zval"].sort_values(ascending=False)
                if len(sorted_vals) >= norm_count:
                    peak_val = sorted_vals.iloc[0]
                    norm_offset = norm_target - peak_val
                    dff["zval"] += norm_offset

            z_title = f"Power [{'dBc' if norm_enable else 'dBFS'}]"
            cmin = zmin if zmin is not None else CONFIG["zmin_amp"]
            cmax = zmax if zmax is not None else CONFIG["zmax_amp"]

        # ------------------------- 4) Zoombereich & Achsenbereich
        if dff.empty:
            x_data = df[x_key]
            y_data = df[y_key]
        else:
            x_data = dff[x_key]
            y_data = dff[y_key]
        auto_x = [x_data.min(), x_data.max()]
        auto_y = [y_data.min(), y_data.max()]
        has_zoom = relayout and "xaxis.range[0]" in relayout
        x_range = [relayout["xaxis.range[0]"], relayout["xaxis.range[1]"]] if has_zoom else auto_x
        y_range = [relayout["yaxis.range[0]"], relayout["yaxis.range[1]"]] if has_zoom else auto_y

        # ------------------------- 5) Deduplizieren (stabil wie original)
        original_points = len(dff)
        always_keep_top_n = int(CONFIG.get("always_keep_top_n", 300))
        loudest_keep = dff.sort_values("zval", ascending=False).head(max(always_keep_top_n, 0)).copy()

        use_lod = False
        if not detailed_mode and not dff.empty:
            x_lo, x_hi = x_range
            y_lo, y_hi = y_range
            if (x_hi > x_lo) and (y_hi > y_lo) and ((y_hi - y_lo) > (USRP_MAX_AUTO - USRP_MIN_AUTO) * 0.5):
                bx = int((x_hi - x_lo) / ((x_hi - x_lo) / 500))
                by = int((y_hi - y_lo) / ((y_hi - y_lo) / 500))
                dff["x_bin"] = ((dff[x_key] - x_lo) / (x_hi - x_lo) * bx).astype(int)
                dff["y_bin"] = ((dff[y_key] - y_lo) / (y_hi - y_lo) * by).astype(int)
                dff = (
                    dff.sort_values("zval", ascending=False)
                    .drop_duplicates(["x_bin", "y_bin"])
                )
                dff = pd.concat([dff, loudest_keep], ignore_index=True)
                dff = dff.drop_duplicates(subset=["rfsg_ghz", "usrp_ghz"], keep="first")
                use_lod = True

        shown_points = len(dff)
        hidden_points = max(original_points - shown_points, 0)
        reduction_pct = (hidden_points / original_points * 100.0) if original_points else 0.0

        if detailed_mode:
            binning_status = f"Detailed mode active: binning OFF | showing all {original_points:,} points."
        elif use_lod:
            binning_status = (
                f"Binned mode active: ON | shown {shown_points:,} / {original_points:,} points "
                f"({hidden_points:,} hidden, {reduction_pct:.1f}% reduction) | "
                f"loudest {max(always_keep_top_n, 0):,} always preserved."
            )
        else:
            binning_status = f"Binned mode active: OFF | showing {original_points:,} points."

        dff = dff.sort_values("zval", ascending=True)

        # ------------------------- 6) Plot
        fig = go.Figure(go.Scattergl(
            x=dff[x_key],
            y=dff[y_key],
            mode="markers",
            marker=dict(
                color=dff["zval"],
                colorscale=CONFIG["colorscale"],
                cmin=cmin, cmax=cmax,
                size=CONFIG["marker_size"],
                symbol=CONFIG["marker_symbol"],
                colorbar=dict(title=z_title),
            ),
            hovertemplate=(
                f"{x_lab} = %{{x:.6f}} GHz<br>"
                f"{y_lab} = %{{y:.6f}} GHz<br>"
                f"{z_title} = %{{marker.color:.3f}}<extra></extra>"
            ),
            showlegend=False,
        ))

        # ------------------------------------------------------------------
        #   MESSBÄNDER EINZEICHNEN (USRP) – PERFORMANT
        # ------------------------------------------------------------------
        if show_bands and USRP_CENTERS and USRP_BW_GHZ:
            hb = USRP_BW_GHZ / 2
            band_vals = [(cf - hb, cf + hb) for cf in USRP_CENTERS]

            band_x = []
            band_y = []

            for band_min, band_max in band_vals:
                if y_key == "usrp_ghz":
                    band_y += [band_min, band_min, None, band_max, band_max, None]
                    band_x += [x_range[0], x_range[1], None, x_range[0], x_range[1], None]
                elif x_key == "usrp_ghz":
                    band_x += [band_min, band_min, None, band_max, band_max, None]
                    band_y += [y_range[0], y_range[1], None, y_range[0], y_range[1], None]

            if band_x and band_y:
                fig.add_trace(go.Scattergl(
                    x=band_x,
                    y=band_y,
                    mode="lines",
                    line=dict(color="gray", dash="dash", width=2),
                    hoverinfo="skip",
                    showlegend=False,
                    name="Measurement Bands"
                ))

        fig.update_xaxes(
            title=x_lab, range=x_range,
            showgrid=True, gridwidth=CONFIG["grid_w_major"],
            gridcolor=CONFIG["grid_col_major"], zeroline=False,
            minor=dict(showgrid=True, gridwidth=CONFIG["grid_w_minor"], gridcolor=CONFIG["grid_col_minor"]),
        )
        fig.update_yaxes(
            title=y_lab, range=y_range,
            showgrid=True, gridwidth=CONFIG["grid_w_major"],
            gridcolor=CONFIG["grid_col_major"], zeroline=False,
            minor=dict(showgrid=True, gridwidth=CONFIG["grid_w_minor"], gridcolor=CONFIG["grid_col_minor"]),
        )

        fig.update_layout(
            title="Intensity Plot",
            height=CONFIG["intensity_height"],
            margin=dict(t=50, b=40),
            legend=dict(orientation="h", x=0, xanchor="left", y=-0.12),
            uirevision="intensity-fixed"
        )

        return fig, [y_min, y_max], binning_status

    @app.callback(
        Output("spectrum-plot", "clickData"),
        Input("sweep-interval", "n_intervals"),
        State("sweep-enable", "value"),
        State("spectrum-plot", "clickData"),
        State("reverse-spectrum-view", "value"),
    )
    def spectrum_sweep_callback(n_intervals, sweep_enabled, last_click, reverse):
        if not sweep_enabled:
            return no_update

        # Achsen-Konfiguration
        axes = get_axes_config("spectrum", reverse_spectrum=reverse)
        x_key = axes["x_key"]
        sweep_key = axes["sweep_key"]

        # Werte exakt aus df holen – KEINE Rundung
        sweep_vals = np.array(sorted(set(df[sweep_key].values)))
        if sweep_vals.size == 0:
            return no_update

        # Aktueller Wert aus clickData holen
        if last_click and "points" in last_click and last_click["points"]:
            pt = last_click["points"][0]
            val = pt.get("x") if sweep_key == x_key else pt.get("y")
            if val is None:
                val = sweep_vals[0]
        else:
            val = sweep_vals[0]

        # Aktuellen Index exakt finden
        idx = np.argwhere(np.isclose(sweep_vals, val, rtol=1e-12, atol=1e-12)).flatten()
        idx = idx[0] if idx.size > 0 else 0
        next_val = sweep_vals[(idx + 1) % len(sweep_vals)]

        # Dummy-Koordinate auf anderer Achse bestimmen
        dummy_rfsg = df["rfsg_ghz"].min()
        dummy_usrp = df["usrp_ghz"].min()

        # clickData setzen
        if sweep_key == "rfsg_ghz":
            return {
                "points": [{
                    "x": float(next_val) if x_key == "rfsg_ghz" else float(dummy_rfsg),
                    "y": float(dummy_usrp) if x_key == "rfsg_ghz" else float(next_val)
                }]
            }
        else:  # sweep_key == "usrp_ghz"
            return {
                "points": [{
                    "x": float(next_val) if x_key == "usrp_ghz" else float(dummy_usrp),
                    "y": float(dummy_rfsg) if x_key == "usrp_ghz" else float(next_val)
                }]
            }














    # -----------------------------------------------------------------------
    # SPECTRUM-PLOT
    # -----------------------------------------------------------------------
    @app.callback(
        Output("spectrum-plot",  "figure"),
        Output("spectrum-amp",   "style"),
        Output("spectrum-refresh-time", "data"),
        Output("spectrum-npoints",      "data"),
        # --------------------- Eingänge -------------------------------
        Input("intensity-plot", "clickData"),
        Input("spectrum-plot",  "clickData"),
        Input("spectrum-plot",  "relayoutData"),
        Input("norm-enable", "value"),  Input("norm-target", "value"),
        Input("show-bands",  "value"),  Input("zaxis-type",   "value"),
        Input("swap-axes",   "value"),
        Input("y_min", "value"), Input("y_max", "value"),
        Input("x_min", "value"), Input("x_max", "value"),
        Input("reverse-spectrum-view", "value"),
    )
    def update_spectrum(
        intensity_click, spectrum_click, relayout,
        norm_enable, norm_target,
        show_bands, z_type, swap_axes,
        y_min, y_max, x_min, x_max, reverse_spectrum_view,
    ):
        t0 = time.perf_counter()

        # ① --- Wer hat getriggert?  ---------------------------------------
        trig_id   = callback_context.triggered[0]["prop_id"]
        click_src = "spectrum" if trig_id.startswith("spectrum-plot.clickData") else "intensity"
        click_data = spectrum_click if click_src == "spectrum" else intensity_click

        # ② --- Achsen-Konfigurationen holen  ------------------------------
        spec_axes = get_axes_config("spectrum",  reverse_spectrum=reverse_spectrum_view)
        int_axes  = get_axes_config("intensity", swap_axes=swap_axes)

        x_key       = spec_axes["x_key"]          # X-Achse im Spectrum
        x_label     = spec_axes["x_label"]
        sweep_key   = spec_axes["sweep_key"]      # konstante Achse (RFSG / USRP)
        sweep_label = spec_axes["sweep_label"]

        # ③ --- Sweep-Wert aus Click bestimmen  ----------------------------
        if click_data and click_data.get("points"):
            pt = click_data["points"][0]

            if click_src == "spectrum":
                # Im Spectrum-Plot liegt die Frequenz IMMER auf X,
                # Y enthält Amplitude → einfach den x-Wert nehmen
                sweep_val = pt["x"] if sweep_key == x_key else pt["y"]
            else:  # Click kam aus Intensity
                prov_axes = int_axes
                sweep_val = (
                    pt["x"] if prov_axes["x_key"] == sweep_key
                    else pt["y"]
                )
        else:
            sweep_val = RFSG_MIN_AUTO if sweep_key == "rfsg_ghz" else USRP_MIN_AUTO

        # ④ --- Daten vorbereiten  ----------------------------------------
        sub = df[np.isclose(df[sweep_key], sweep_val)].copy()

        # X-Zoom (falls vorhanden) anwenden
        if relayout and "xaxis.range[0]" in relayout:
            lo, hi = relayout["xaxis.range[0]"], relayout["xaxis.range[1]"]
            sub = sub[(sub[x_key] >= lo) & (sub[x_key] <= hi)]

        # Normalisierung (nur bei RFSG-Sweep)
        if norm_enable and norm_target is not None and sweep_key == "rfsg_ghz":
            sub["amp"] += norm_target - REF_AMP.get(sweep_val, 0)

        # Y-Achse wählen
        if z_type == "IQ" and has_iq:
            y_col, y_label = "IQ", "IQ"
        else:
            y_col   = "amp"
            y_label = "Amplitude [dBc]" if norm_enable else "Amplitude [dBFS]"

        # ⑤ --- Figure bauen  ---------------------------------------------
        fig = go.Figure(go.Scatter(
            x=sub[x_key],
            y=sub[y_col],
            mode="lines+markers",
            marker=dict(size=CONFIG["marker_size"]),
            hovertemplate=(
                f"{x_label.split()[0]} = %{{x:.6f}} GHz<br>"
                f"{y_label} = %{{y:.2f}}<extra></extra>"
            ),
        ))

        # Mess-Bänder (schneller via Scattergl-Linien)
        if show_bands and USRP_CENTERS and USRP_BW_GHZ and x_key == "usrp_ghz":
            hb = USRP_BW_GHZ / 2
            y_vals = [sub[y_col].min(), sub[y_col].max()] if len(sub) else [0, 1]
            line_x = []
            line_y = []
            for cf in USRP_CENTERS:
                for x in (cf - hb, cf + hb):
                    line_x += [x, x, None]
                    line_y += [y_vals[0], y_vals[1], None]

            fig.add_trace(go.Scattergl(
                x=line_x,
                y=line_y,
                mode="lines",
                line=dict(color="gray", dash="dash"),
                hoverinfo="skip",
                showlegend=False
            ))

        # Achsen-Ranges
        x_range = [x_min, x_max] if x_key == "rfsg_ghz" else [y_min, y_max]
        fig.update_xaxes(title=x_label, range=x_range)
        fig.update_yaxes(title=y_label)

        fig.update_layout(
            title=f"Spectrum @ {sweep_label}: {format_sig(sweep_val)} GHz",
            height=CONFIG["spectrum_height"], margin=dict(t=30, b=30),
            uirevision="spectrum-fixed"
        )

        # Y-Zoom erhalten
        if relayout and "yaxis.range[0]" in relayout:
            fig.update_yaxes(range=[
                relayout["yaxis.range[0]"], relayout["yaxis.range[1]"]
            ])

        # Performance-Infos
        refresh_time = time.perf_counter() - t0
        n_points     = len(sub)

        # Spektrum-Amp-Trace nur bei „amp“
        amp_style = {"display": "none"} if z_type == "IQ" else {"display": "block"}

        return fig, amp_style, refresh_time, n_points





# --- Peak-Tabelle -------------------------------------------------------------
# ---------------------------------------------------------------------------
#   PEAK-TABLE CALLBACK  –  funktioniert MIT und OHNE Axis-Swap
# ---------------------------------------------------------------------------
    @app.callback(
        Output("peak-table", "data"),
        Output("peak-table", "columns"),
        Input("spectrum-plot", "relayoutData"),
        Input("spectrum-plot", "clickData"),
        Input("intensity-plot", "clickData"),
        Input("norm-enable", "value"),
        Input("norm-target", "value"),
        Input("peak-mode-input", "value"),
        Input("peak-count", "value"),
        Input("peak-threshold", "value"),
        Input("sort-mode", "value"),
        Input("zaxis-type", "value"),
        Input("reverse-spectrum-view", "value"),
    )
    def update_peaks(relayout, spectrum_click, intensity_click,
                     norm_enable, norm_target,
                     mode, count, threshold,
                     sort_mode, z_type,
                     reverse_spectrum_view):
        """
        Füllt und sortiert die Peak-Tabelle entsprechend der aktuellen Spektrum-Ansicht.
        """

        # 1) Wähle das korrekte clickData
        triggered = callback_context.triggered[0]["prop_id"]
        if triggered.startswith("spectrum-plot.clickData"):
            click_data = spectrum_click
        else:
            click_data = intensity_click

        # 2) Hol Achsen-Definition für Spectrum
        axes = get_axes_config("spectrum", reverse_spectrum=reverse_spectrum_view)
        x_key = axes["x_key"]
        sweep_key = axes["sweep_key"]
        x_label = axes["x_label"]

        # 3) Bestimme Sweep-Wert aus dem Klick
        if click_data and "points" in click_data and click_data["points"]:
            pt = click_data["points"][0]
            sweep_val = pt.get("y") if sweep_key != x_key else pt.get("x")
        else:
            # Default, falls kein Klick
            sweep_val = RFSG_MIN_AUTO if sweep_key == "rfsg_ghz" else USRP_MIN_AUTO

        # 4) Filtere DataFrame auf die Sweep-Linie
        sub = df[np.isclose(df[sweep_key], sweep_val)].copy()

        # Wenn IQ angefordert und sub leer ist, dann auf die andere Achse ausweichen
        if z_type == "IQ" and has_iq and sub["IQ"].isna().all():
            # Sweep-Key umkehren
            alt_key = "usrp_ghz" if sweep_key == "rfsg_ghz" else "rfsg_ghz"
            sub = df[np.isclose(df[alt_key], sweep_val)].copy()

        # 5) Anwenden des Zoom-Bereichs, falls vorhanden
        if relayout and "xaxis.range[0]" in relayout and "xaxis.range[1]" in relayout:
            lo, hi = relayout["xaxis.range[0]"], relayout["xaxis.range[1]"]
            sub = sub[(sub[x_key] >= lo) & (sub[x_key] <= hi)]

        # 6) Normierung im RFSG-Modus
        if norm_enable and norm_target is not None and sweep_key == "rfsg_ghz" and z_type == "amp":
            sub["amp"] += norm_target - REF_AMP.get(sweep_val, 0)

        # 7) Z-Spalte wählen
        sub["zval"] = sub["IQ"] if (z_type == "IQ" and has_iq) else sub["amp"]

        # 8) Peaks extrahieren
        if mode == "count":
            peaks = sub.nlargest(int(max(count, 1)), "zval")
        else:
            peaks = sub[sub["zval"] >= threshold]

        # 9) Sortierung
        ascending = (sort_mode == "freq")
        sort_col = x_key if ascending else "zval"
        peaks = peaks.sort_values(sort_col, ascending=ascending).reset_index(drop=True)

        # 10) Formatierung für DataTable
        peaks = peaks.rename(columns={x_key: "xval"})
        peaks["xval"] = peaks["xval"].round(6)
        peaks["zval"] = peaks["zval"].round(3 if z_type == "IQ" else 1)
        for col in OPT:
            peaks[col] = peaks[col].round(3) if col in peaks else "NA"

        unit = "IQ" if z_type == "IQ" else ("dBc" if norm_enable else "dBFS")
        columns = (
            [{"name": x_label, "id": "xval"},
             {"name": "IQ" if z_type == "IQ" else f"Power [{unit}]", "id": "zval"}]
            + [{"name": col, "id": col} for col in OPT]
        )

        return peaks.to_dict("records"), columns


    @app.callback(
        Output("sweep-interval", "interval"),
        Output("sweep-interval", "disabled"),
        Input("sweep-enable", "value"),
        Input("sweep-wait", "value"),
    )
    def toggle_sweep_interval(sweep_on, wait):
        if not sweep_on or wait is None or wait <= 0:
            return 1000, True
        interval_ms = int(max(wait, 0.1) * 1000)
        return interval_ms, False

    # ---------------------------------------------------------------------------
    #  INTENSITY-POINT-COUNTER
    # ---------------------------------------------------------------------------
    @app.callback(
        Output("intensity-count", "children"),
        Input("zmin", "value"), Input("zmax", "value"),
        Input("x_min", "value"), Input("x_max", "value"),
        Input("y_min", "value"), Input("y_max", "value"),
        Input("swap-axes", "value"),
        Input("zaxis-type", "value"),
        Input("intensity-plot", "relayoutData"),
    )
    def update_intensity_count(
        zmin, zmax, rfsg_min, rfsg_max, usrp_min, usrp_max,
        swap_axes, z_type, relayout
    ):
        # Achsen‐Info (identisch zur Plot-Funktion)
        a = get_axes_config("intensity", swap_axes=swap_axes)
        x_key, y_key = a["x_key"], a["y_key"]

        # Aktuelle Zoom-Ranges
        x0 = relayout.get("xaxis.range[0]", rfsg_min if x_key=="rfsg_ghz" else usrp_min) if relayout else \
            (rfsg_min if x_key=="rfsg_ghz" else usrp_min)
        x1 = relayout.get("xaxis.range[1]", rfsg_max if x_key=="rfsg_ghz" else usrp_max) if relayout else \
            (rfsg_max if x_key=="rfsg_ghz" else usrp_max)
        y0 = relayout.get("yaxis.range[0]", usrp_min if y_key=="usrp_ghz" else rfsg_min) if relayout else \
            (usrp_min if y_key=="usrp_ghz" else rfsg_min)
        y1 = relayout.get("yaxis.range[1]", usrp_max if y_key=="usrp_ghz" else rfsg_max) if relayout else \
            (usrp_max if y_key=="usrp_ghz" else rfsg_max)

        # Filter
        sub = df[(df[x_key].between(x0, x1)) & (df[y_key].between(y0, y1))]

        if z_type == "IQ" and has_iq:
            sub = sub[sub["IQ"].between(zmin or 0, zmax or 1)]
        else:
            lo = zmin if zmin is not None else CONFIG["zmin_amp"]
            hi = zmax if zmax is not None else CONFIG["zmax_amp"]
            sub = sub[sub["amp"].between(lo, hi)]

        n   = len(sub)
        col = "#1fa51f" if n <= 1e5 else "#d90000" if n >= 5e5 else "#ff9f00"
        return html.Span(
            f"Number of displayed points: {n}",
            style={"color": col, "fontWeight": "bold"},
        )

    # ---------------------------------------------------------------------------
    #  Hilfs-Funktion: grobe Browser-Renderzeit in Sekunden abschätzen
    # ---------------------------------------------------------------------------
    def estimate_browser_render_time(n_points: int) -> float:
        """
        Schätzt die zusätzliche Render-Latenz im Browser für ScatterGL:
            0.05 s Grundlast  +  30 µs pro Punkt
        Passen Sie die Konstanten bei Bedarf an Ihre HW an.
        """
        return 0.05 + 0.00003 * n_points

    @app.callback(
        Output("spectrum-refresh-time-display", "children"),
        Input("spectrum-refresh-time", "data"),
        Input("spectrum-npoints", "data"),
    )
    def show_refresh_time(refresh_time, n_points):
        if refresh_time is None or n_points is None:
            return ""
        browser_time = estimate_browser_render_time(n_points)
        dwell_time = refresh_time + browser_time
        return f"Recommended min Dwell Time: {dwell_time:.3f} s "
    


    # ---------------------------------------------------------------------------
    #  SPECTRUM-POINT-COUNTER
    # ---------------------------------------------------------------------------
    @app.callback(
        Output("spectrum-count", "children"),
        # — Eingänge —
        Input("intensity-plot",  "clickData"),          # Klicks aus dem oberen Plot
        Input("spectrum-plot",   "clickData"),          # Klicks im Spectrum
        Input("spectrum-plot",   "relayoutData"),       # X-Zoom/Relayout
        Input("sweep-interval",  "n_intervals"),        # Sweep-Timer (nur Trigger)
        Input("swap-axes",       "value"),              # Zustand des Axis-Swap
        Input("reverse-spectrum-view", "value"),        # RFSG↔USRP-Tausch
    )
    def update_spectrum_count(
        inten_click, spec_click, relayout, _n_int, swap_axes, reverse_spectrum_view
    ):
        # ------------------------------------------------ 1) Welche Quelle hat getriggert?
        trig_id = callback_context.triggered[0]["prop_id"]
        if trig_id.startswith("spectrum-plot.clickData"):
            click_data  = spec_click
            provider_ax = get_axes_config("spectrum",
                                        reverse_spectrum=reverse_spectrum_view)
        else:
            click_data  = inten_click
            provider_ax = get_axes_config("intensity", swap_axes=swap_axes)

        spec_ax   = get_axes_config("spectrum",
                                    reverse_spectrum=reverse_spectrum_view)
        sweep_key = spec_ax["sweep_key"]          # konstante Achse (RFSG oder USRP)
        x_key     = spec_ax["x_key"]              # X-Achse des Spectrum-Plots

        # ------------------------------------------------ 2) Sweep-Wert aus Klick holen
        if click_data and "points" in click_data and click_data["points"]:
            pt = click_data["points"][0]
            if provider_ax["x_key"] == sweep_key:
                sweep_val = pt["x"]
            elif provider_ax.get("y_key") == sweep_key:
                sweep_val = pt["y"]
            else:                                    # Fallback (sollte nie passieren)
                sweep_val = RFSG_MIN_AUTO if sweep_key == "rfsg_ghz" else USRP_MIN_AUTO
        else:
            sweep_val = RFSG_MIN_AUTO if sweep_key == "rfsg_ghz" else USRP_MIN_AUTO

        # ------------------------------------------------ 3) Daten einschränken
        sub = df[np.isclose(df[sweep_key], sweep_val)]

        if relayout and "xaxis.range[0]" in relayout and "xaxis.range[1]" in relayout:
            lo, hi = relayout["xaxis.range[0]"], relayout["xaxis.range[1]"]
            sub = sub[(sub[x_key] >= lo) & (sub[x_key] <= hi)]

        n_points = len(sub)

        # ------------------------------------------------ 4) Farb-Logik
        def points_to_color(n):
            if n <= 100_000:
                return "#1fa51f"
            if n >= 500_000:
                return "#d90000"
            if n >= 200_000:
                f = (n - 200_000) / 300_000
                r = int(255 + (217 - 255) * f)
                g = int(216 + (  0 - 216) * f)
                return f"rgb({r},{g},0)"
            f = (n - 100_000) / 100_000
            r = int(31  + (255 - 31)  * f)
            g = int(165 + (216 - 165) * f)
            return f"rgb({r},{g},31)"

        return html.Span(
            f"Number of displayed points in spectrum: {n_points}",
            style={"color": points_to_color(n_points), "fontWeight": "bold"},
        )


    # -----------------------------------------------------------------------
    # TXT-REPORT-DOWNLOAD
    # -----------------------------------------------------------------------
    @app.callback(
        Output("download-report", "data"),
        Input("download-report-btn", "n_clicks"),
        State("zmin", "value"), State("zaxis-type", "value"),
        State("norm-enable", "value"), State("norm-target", "value"),
        State("x_min", "value"), State("x_max", "value"),
        State("y_min", "value"), State("y_max", "value"),
        State("swap-axes", "value"),
        prevent_initial_call=True,
    )
    def download_report(
        n, zmin, z_type, norm_en, norm_target,
        x_min, x_max, y_min, y_max, swap
    ):
        txt = build_report(
            df, has_iq, REF_AMP, OPT, CONFIG,
            zmin, z_type, norm_en, norm_target,
            x_min, x_max, y_min, y_max,
            swap
        )
        return {
            "content": txt,
            "filename": "spur_report.txt",
            "type": "text/plain"
        }
