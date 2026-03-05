from dash import Dash, dcc, html, dash_table
import dash_bootstrap_components as dbc
from settings import CONFIG, REQ, OPT
from data import load_csv, parse_metadata, load_dataframe, check_warnings, prepare_dataframe, build_reference_maps, get_axis_limits
from layout import build_controls, build_range_settings, build_peak_controls, build_sweep_and_axis_controls
from callbacks import register_callbacks

# 1. Load data
import data  # Import the whole module to access the file dialog cache

import logging
import warnings

# ——— Logging / Warnings konfigurieren ———
warnings.filterwarnings("ignore", message="DataFrame columns are not unique.*")
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("dash").setLevel(logging.ERROR)

import dash

file_path = data.load_csv()  # Always use the cached version from data.py
USRP_CENTERS, USRP_BW_GHZ = parse_metadata(file_path)
df = load_dataframe(file_path)
warnings = check_warnings(df)
df, has_iq = prepare_dataframe(df)
REF_AMP, REF_USRP = build_reference_maps(df)
RFSG_MIN_AUTO, RFSG_MAX_AUTO, USRP_MIN_AUTO, USRP_MAX_AUTO = get_axis_limits(df)

# 2. Create Dash app
app = Dash(__name__, external_stylesheets=[dbc.themes.MINTY])
app.title = "Interactive Spur Viewer"

controls = build_controls(has_iq)
range_settings = build_range_settings(RFSG_MIN_AUTO, RFSG_MAX_AUTO, USRP_MIN_AUTO, USRP_MAX_AUTO)
peak_controls = build_peak_controls()
sweep_interval = dcc.Interval(id="sweep-interval", interval=1000, n_intervals=0, disabled=True)
spectrum_axis_controls = build_sweep_and_axis_controls()

app.layout = dbc.Container(
    fluid=True,
    className="app-shell",
    children=[
        html.Div(
            className="hero-header",
            children=[
                html.Div(
                    [
                        html.H2("Interactive Spur Viewer", className="hero-title"),
                        html.P("Visualization and analysis of spectral data", className="hero-subtitle"),
                    ]
                ),
                html.Div(
                    className="hero-chip",
                    children=[
                        html.Span("Loaded samples", className="hero-chip-label"),
                        html.Strong(f"{len(df):,}"),
                    ],
                ),
            ],
        ),
        controls,
        range_settings,
        html.Div(className="plot-card", children=[dcc.Graph(id="intensity-plot", config={"displayModeBar": False})]),
        html.Div([
            html.Span("— Gray dashed lines = Band boundaries (CF ± BW/2)", style={"fontStyle": "italic"}),
            html.Br(),
            html.Span(id="intensity-count", style={"fontWeight": "bold", "marginLeft": "0.5rem"}),
            html.Br(),
            html.Span(id="binning-status", style={"fontWeight": "bold", "marginLeft": "0.5rem"}),
        ], className="hint-text"),

        sweep_interval,
        spectrum_axis_controls,
        html.Div(className="plot-card", children=[dcc.Graph(id="spectrum-plot")]),
        html.Div(id="spectrum-count", className="hint-text"),
        dcc.Store(id="spectrum-refresh-time", storage_type="memory"),
        html.Div(id="spectrum-refresh-time-display", className="hint-text"),
        html.Div(
            dcc.Graph(id="spectrum-amp"),
            id="spectrum-amp-wrapper",
            style={"display": "none"}
        ) if has_iq else html.Div(),
        peak_controls,
        html.H5("Top Peaks", className="section-heading"),
        html.Div(
            className="table-card",
            children=[
                dash_table.DataTable(
                    id="peak-table",
                    style_cell={"textAlign": "center", "padding": "0.5rem"},
                    style_table={"overflowX": "auto"},
                ),
            ],
        ),
        html.Div([
            html.Strong("Warnings: "),
            html.Ul([html.Li(w) for w in warnings]) if warnings else html.Span("None"),
        ], className="warning-box"),
        dcc.Store(id="usrp-xrange", storage_type="memory"),
        dcc.Store(id="spectrum-npoints", storage_type="memory"),
    ],
)

register_callbacks(app, df, has_iq, REF_AMP, REF_USRP, USRP_CENTERS, USRP_BW_GHZ, RFSG_MIN_AUTO, RFSG_MAX_AUTO, USRP_MIN_AUTO, USRP_MAX_AUTO, warnings)

if __name__ == "__main__":
    debug_flag = CONFIG.get("debug_mode", False)
    host = CONFIG.get("host", "127.0.0.1")
    port = CONFIG.get("port", 8050)
    url = f"http://{host}:{port}"
    print(f"\nÖffne Dashboard im Browser: {url}")
    app.run(debug=debug_flag, host=host, port=port)
