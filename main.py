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
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Interactive Spur Viewer"

controls = build_controls(has_iq)
range_settings = build_range_settings(RFSG_MIN_AUTO, RFSG_MAX_AUTO, USRP_MIN_AUTO, USRP_MAX_AUTO)
peak_controls = build_peak_controls()
spectrum_controls = build_sweep_and_axis_controls()
sweep_interval = dcc.Interval(id="sweep-interval", interval=1000, n_intervals=0, disabled=True)
spectrum_axis_controls = build_sweep_and_axis_controls()

app.layout = dbc.Container(
    fluid=True,
    children=[
        html.Div([
            html.H2(
                "Interactive Spur Viewer",
                style={
                    "fontWeight": "bold",
                    "letterSpacing": "0.05em",
                    "color": "#22223b",
                    "fontFamily": "Segoe UI, Arial, sans-serif",
                    "margin": 0,
                }
            ),
            html.Span(
                "Visualization and analysis of spectral data",
                style={
                    "marginLeft": "1.5rem",
                    "fontSize": "1.1rem",
                    "color": "#555",
                    "verticalAlign": "middle",
                }
            ),
        ], style={"textAlign": "left", "marginTop": "1.5rem", "marginBottom": "0.5rem"}),
        html.Hr(),
        controls,
        range_settings,
        dcc.Graph(id="intensity-plot", config={"displayModeBar": False}),
        html.Div([
            html.Span("— Gray dashed lines = Band boundaries (CF ± BW/2)", style={"fontStyle": "italic"}),
            html.Br(),
            html.Span(id="intensity-count", style={"fontWeight": "bold", "marginLeft": "0.5rem"}),
        ], style={"marginBottom": "1rem"}),
        html.Div("Top plot shows an intensity map of the selected Z-axis.",
                 style={"marginBottom": "1rem"}),

        sweep_interval,
        spectrum_axis_controls,  # ← NEU hinzugefügt
        dcc.Graph(id="spectrum-plot"),
        html.Div(id="spectrum-count", style={"marginBottom": "1rem", "fontWeight": "bold"}),
        dcc.Store(id="spectrum-refresh-time", storage_type="memory"),
        html.Div(id="spectrum-refresh-time-display", style={"marginBottom": "1rem", "fontWeight": "bold"}),
        html.Div(
            dcc.Graph(id="spectrum-amp"),
            id="spectrum-amp-wrapper",
            style={"display": "none"}  # Start hidden; wird nur bei Bedarf sichtbar gemacht
        ) if has_iq else html.Div(),
        peak_controls,
        html.H5("Top Peaks"),
        dash_table.DataTable(
            id="peak-table",
            style_cell={"textAlign": "center"},
            style_table={"overflowX": "auto"},
        ),
        html.Div([
            html.Strong("Warnings: "),
            html.Ul([html.Li(w) for w in warnings]) if warnings else html.Span("None"),
        ], style={"marginTop": "1rem", "color": "firebrick"}),
        dcc.Store(id="usrp-xrange", storage_type="memory"),
        dcc.Store(id="spectrum-npoints", storage_type="memory"),
    ],
)

register_callbacks(app, df, has_iq, REF_AMP, REF_USRP, USRP_CENTERS, USRP_BW_GHZ, RFSG_MIN_AUTO, RFSG_MAX_AUTO, USRP_MIN_AUTO, USRP_MAX_AUTO, warnings)

if __name__ == "__main__":
    # Debug-Flag, Host und Port aus den Settings laden
    debug_flag = CONFIG.get("debug_mode", False)
    host      = CONFIG.get("host", "127.0.0.1")
    port      = CONFIG.get("port", 8050)
    # URL für das Dashboard
    url = f"http://{host}:{port}"
    print(f"\nÖffne Dashboard im Browser: {url}")
    # Server starten
    app.run(debug=debug_flag, host=host, port=port)

