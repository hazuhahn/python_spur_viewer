from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
from settings import CONFIG, OPT


# ---------------------------------------------------------------------------
#   HILFSFUNKTION FÜR ACHSENDATEN
# ---------------------------------------------------------------------------
def get_axes_config(plot_type, swap_axes=False, reverse_spectrum=False):
    """
    Gibt die Achsen-Konfiguration für einen Plot zurück.

    Args:
        plot_type (str): "intensity" oder "spectrum"
        swap_axes (bool): Für "intensity" → tauscht RFSG/USRP-Achsen
        reverse_spectrum (bool): Für "spectrum" → USRP/RFSG-Achse tauschen

    Returns:
        dict: Enthält x_key, y_key (für intensity), Labels und ggf. sweep_key
    """
    if plot_type == "intensity":
        if not swap_axes:
            return {
                "x_key": "rfsg_ghz",
                "y_key": "usrp_ghz",
                "x_label": "RFSG Frequency [GHz]",
                "y_label": "USRP Frequency [GHz]",
                "sweep_key": "rfsg_ghz",
                "sweep_label": "RFSG Frequency [GHz]",
            }
        else:
            return {
                "x_key": "usrp_ghz",
                "y_key": "rfsg_ghz",
                "x_label": "USRP Frequency [GHz]",
                "y_label": "RFSG Frequency [GHz]",
                "sweep_key": "usrp_ghz",
                "sweep_label": "USRP Frequency [GHz]",
            }

    elif plot_type == "spectrum":
        if not reverse_spectrum:
            return {
                "x_key": "usrp_ghz",
                "x_label": "USRP Frequency [GHz]",
                "sweep_key": "rfsg_ghz",
                "sweep_label": "RFSG Frequency [GHz]",
            }
        else:
            return {
                "x_key": "rfsg_ghz",
                "x_label": "RFSG Frequency [GHz]",
                "sweep_key": "usrp_ghz",
                "sweep_label": "USRP Frequency [GHz]",
            }

    else:
        raise ValueError(f"Unsupported plot type: {plot_type}")



# ---------------------------------------------------------------------------
#   CONTROL-BEREICH  (inkl. Download-Button für TXT-Report)
# ---------------------------------------------------------------------------
def build_controls(has_iq):
    return html.Div([
        dbc.Row([
            dbc.Col(
                dbc.Button(
                    "Download Spur-Report",
                    id="download-report-btn",
                    color="primary",
                    className="me-3",
                ),
                width="auto",
            ),
            dcc.Download(id="download-report"),
        ], className="mb-3", align="center"),

        dbc.Row([
            dbc.Col(dbc.Switch(id="show-bands", label="Show Measurement Bands",
                               value=CONFIG["show_bands"], className="me-4"), width="auto"),
            dbc.Col(dbc.Switch(id="norm-enable", label="Enable Normalization",
                               value=CONFIG["norm_enable"], className="me-4"), width="auto"),
            dbc.Col(dbc.Switch(id="show-usrp-band", label="Show USRP Band",
                               value=CONFIG["show_usrp_band"], className="me-4"), width="auto"),
            dbc.Col(dbc.Switch(id="swap-axes", label="Swap X/Y Axes",
                               value=False, className="me-4"), width="auto"),
        ], className="mb-3", align="center"),

        dbc.Row([
            dbc.Col(html.Div([
                html.Label("Normalize to [dBc]", className="form-label"),
                dcc.Input(id="norm-target", type="number",
                          value=CONFIG["norm_target"], className="form-control"),
            ]), width="auto"),
            dbc.Col(html.Div([
                html.Label("USRP Bandwidth [MHz]", className="form-label"),
                dcc.Input(id="usrp-bw", type="number",
                          value=CONFIG["usrp_bw_mhz"], className="form-control"),
            ]), width="auto"),
            dbc.Col(html.Div([
                html.Label("Z-Axis", className="form-label"),
                dbc.RadioItems(id="zaxis-type",
                               options=[{"label": "Amplitude", "value": "amp"},
                                        {"label": "IQ", "value": "IQ", "disabled": not has_iq}],
                               value=CONFIG["zaxis_default"], inline=True,
                               label_style={"marginRight": "1rem"},
                               input_checked_style={"backgroundColor": "#0d6efd",
                                                    "borderColor": "#0d6efd",
                                                    "color": "white"}),
            ]), width="auto"),
        ], align="center"),
    ], className="mb-4",
       style={"backgroundColor": "#f8f9fa", "padding": "1rem", "borderRadius": "0.5rem"})


# ---------------------------------------------------------------------------
#   RANGE SETTINGS
# ---------------------------------------------------------------------------
def build_range_settings(RFSG_MIN_AUTO, RFSG_MAX_AUTO, USRP_MIN_AUTO, USRP_MAX_AUTO):
    return html.Div([
        html.H5("Main Plot Settings"),
        dbc.Row([
            dbc.Col(html.Div([
                html.H6("Z-Axis Minimum"),
                dcc.Input(id="zmin", type="number",
                          value=CONFIG["zmin_amp"], className="form-control"),
                html.H6("Z-Axis Maximum", style={"marginTop": "1rem"}),
                dcc.Input(id="zmax", type="number",
                          value=CONFIG["zmax_amp"], className="form-control"),
            ], style={"backgroundColor": "#f8f9fa",
                      "padding": "1rem", "borderRadius": "0.5rem"}), width=6),
            dbc.Col(html.Div([
                html.H6("RFSG Min [GHz]"),
                dcc.Input(id="x_min", type="number",
                          value=RFSG_MIN_AUTO, className="form-control", debounce=True),
                html.H6("RFSG Max [GHz]", style={"marginTop": "1rem"}),
                dcc.Input(id="x_max", type="number",
                          value=RFSG_MAX_AUTO, className="form-control", debounce=True),
            ], style={"backgroundColor": "#f8f9fa",
                      "padding": "1rem", "borderRadius": "0.5rem"}), width=3),
            dbc.Col(html.Div([
                html.H6("USRP Min [GHz]"),
                dcc.Input(id="y_min", type="number",
                          value=USRP_MIN_AUTO, className="form-control", debounce=True),
                html.H6("USRP Max [GHz]", style={"marginTop": "1rem"}),
                dcc.Input(id="y_max", type="number",
                          value=USRP_MAX_AUTO, className="form-control", debounce=True),
            ], style={"backgroundColor": "#f8f9fa",
                      "padding": "1rem", "borderRadius": "0.5rem"}), width=3),
        ], className="mb-4"),
    ])


# ---------------------------------------------------------------------------
#   PEAK-CONTROL-CARD
# ---------------------------------------------------------------------------
def build_peak_controls():
    return dbc.Card([
        dbc.CardHeader("Peak Table Settings"),
        dbc.CardBody(
            dbc.Row([
                dbc.Col(html.Div([
                    html.H6("Peak Selection Mode"),
                    dcc.Dropdown(
                        id="peak-mode-input",
                        options=[{"label": "Top N Peaks", "value": "count"},
                                 {"label": "All ≥ Threshold", "value": "threshold"}],
                        value=CONFIG["peak_mode_default"], clearable=False,
                        className="form-select"),
                ]), width=3),
                dbc.Col(html.Div([
                    html.H6("Number of Peaks"),
                    dcc.Input(id="peak-count", type="number",
                              value=CONFIG["peak_count"], className="form-control"),
                ]), width=3),
                dbc.Col(html.Div([
                    html.H6("Threshold (dBFS/dBc)"),
                    dcc.Input(id="peak-threshold", type="number",
                              value=CONFIG["peak_threshold"], className="form-control"),
                ]), width=3),
                dbc.Col(html.Div([
                    html.Label("Sort By"),
                    dbc.RadioItems(id="sort-mode",
                                   options=[{"label": "Frequency", "value": "freq"},
                                            {"label": "Value", "value": "zval"}],
                                   value=CONFIG["sort_mode_default"], inline=True,
                                   label_style={"marginRight": "1rem"},
                                   input_checked_style={"backgroundColor": "#0d6efd",
                                                        "borderColor": "#0d6efd",
                                                        "color": "white"}),
                ]), width=3),
            ]),
        ),
    ], className="mb-4",
       style={"backgroundColor": "#f8f9fa", "padding": "1rem", "borderRadius": "0.5rem"})


# ---------------------------------------------------------------------------
#   SPECTRUM SETTINGS CARD
# ---------------------------------------------------------------------------
def build_sweep_and_axis_controls():
    return dbc.Card(
        dbc.CardBody([
            html.H5("Spectrum Sweep Settings", className="card-title mb-3"),

            # Beide Switches in einer Zeile
            dbc.Row([
                dbc.Col(dbc.Switch(
                    id="reverse-spectrum-view",
                    label="Show RFSG Spectrum @ fixed USRP",
                    value=CONFIG["reverse_spectrum_default"],
                    className="form-switch"
                ), width="auto", className="me-4"),

                dbc.Col(dbc.Switch(
                    id="sweep-enable",
                    label="Enable Frequency Sweep",
                    value=False,
                    className="form-switch"
                ), width="auto"),
            ], className="mb-3", align="center", justify="start"),

            # Dwell-Time schmaler
            dbc.Row([
                dbc.Col([
                    html.Label("Dwell time per step [s]", className="form-label"),
                    dbc.Input(
                        id="sweep-wait",
                        type="number",
                        min=0.1,
                        step=0.1,
                        value=1.0,
                        className="form-control",
                        style={"maxWidth": "400px"}
                    ),
                ], width="auto"),
            ]),
        ]),
        className="mb-4",
        style={
            "backgroundColor": "#f8f9fa",
            "padding": "1.5rem",
            "borderRadius": "0.5rem",
        }
    )





