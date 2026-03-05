# settings.py
CONFIG: dict[str, object] = {
    # UI defaults -----------------------------------------------------------
    "show_bands": False,
    "norm_enable": False,
    "show_usrp_band": False,
    "reverse_spectrum_default": False,
    "detailed_mode_default": False,

    "zaxis_default": "amp",        # "amp" | "IQ"
    "zmin_amp": -90.0,
    "zmax_amp": 0.0,
    "zmin_iq": 0.0,
    "zmax_iq": 1.0,

    "norm_target": 0.0,            # dBc
    "usrp_bw_mhz": 1000.0,

    "peak_mode_default": "count",  # "count" | "threshold"
    "peak_count": 10,
    "peak_threshold": -60.0,       # dBFS/dBc
    "sort_mode_default": "freq",   # "freq" | "zval"

    # Plot appearance -------------------------------------------------------
    "colorscale": "Inferno",
    "marker_size": 6,
    "marker_symbol": "circle",
    "grid_col_major": "rgba(160,160,160,0.30)",
    "grid_col_minor": "rgba(160,160,160,0.15)",
    "grid_w_major": 1,
    "grid_w_minor": 0.5,

    "lod_target_bins": 450,       # Zielauflösung pro Achse für LOD-Binning
    "lod_min_points": 120000,      # Ab dieser Punktzahl LOD aktivieren
    "always_keep_top_n": 300,      # Lauteste Spurs immer sichtbar halten

    # Layout heights --------------------------------------------------------
    "intensity_height": 700,
    "spectrum_height": 300,

    # Helper-line style -----------------------------------------------------
    "usrp_helper_col": "magenta",
    "usrp_helper_w": 4,
    "usrp_helper_marker": 4,

    # --- Neue Performance-Settings für Chunk-Größe und Engine-Choice ---
    "chunk_target_time": 0.2,       # Zielzeit pro Chunk in Sekunden
    "sample_chunk_rows": 5000,      # Zeilen für Perfomance-Sampling
    "default_chunk_size": 50000,    # Fallback-Chunk-Größe
    "ram_fraction": 0.2,            # Anteil des verfügbaren RAM für Chunks
    "max_chunk_size": 200000,       # Maximal erlaubte Chunk-Größe
    "min_chunk_size": 1000,         # Minimal erlaubte Chunk-Größe

    "auto_polars": True,            # Polars automatisch nutzen, wenn HW passt
    "polars_cpu_threshold": 8,      # Mindestanzahl CPU-Kerne für Polars
    "polars_ram_threshold_gb": 16,  # Mindest-RAM (GB) für Polars

    "use_dask": True,
    # --- CSV Input Settings ---
        "csv_delimiter": ";",         # e.g. "," for US format
        "csv_decimal": ",",           # e.g. "." for US format
        "csv_thousands": None,        # e.g. "," if "1,000" means 1000               # Dask Multi-Core ein-/ausschalten
    "dask_blocksize": None,         # Blockgröße für dask.read_csv (bytes, None=auto)
    "skip_csv_warning": False,

}

REQ = ["rfsg", "usrp", "amp"]

OPT = [
    "IQ_MAX_Absolute", "LF_DSA1", "LF_DSA2",
    "LO_DSA", "LO_PWR", "ADMV_DSA", "RX_RF_DSA",
    "RFSG_Output_Power",
]
