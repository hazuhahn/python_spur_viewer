import re
import tkinter as tk
from tkinter import filedialog
import numpy as np
import pandas as pd
import sys
import time
import os

from settings import CONFIG, REQ, OPT

_selected_file_path = None  # Cache for selected file path


def load_csv():
    env_path = os.environ.get("SPUR_VIEWER_CSV")
    if env_path:
        return env_path

    cached_path = get_selected_file_from_temp()
    if cached_path:
        return cached_path

    root = tk.Tk(); root.withdraw()
    path = filedialog.askopenfilename(
        title="Select CSV File",
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*")]
    )
    return path


def get_selected_file_from_temp():
    try:
        with open(".selected_csv_path.txt", "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except:
        return None


if not _selected_file_path:
    tmp = get_selected_file_from_temp()
    if tmp:
        _selected_file_path = tmp


def parse_metadata(file_path):
    USRP_CENTERS, USRP_BW_GHZ = [], None
    with open(file_path, "r", encoding="utf-8") as fp:
        for line in fp:
            if line.startswith("#CF="):
                try:
                    USRP_CENTERS = [int(v)/1e9 for v in re.split(r"[;,]", line[4:]) if v.strip()]
                except ValueError:
                    pass
            elif line.startswith("#BW="):
                try:
                    USRP_BW_GHZ = int(line[4:])/1e9
                except ValueError:
                    pass
    return USRP_CENTERS, USRP_BW_GHZ


def _candidate_csv_formats():
    cfg_sep = CONFIG.get("csv_delimiter", ";")
    cfg_dec = CONFIG.get("csv_decimal", ",")
    cfg_ths = CONFIG.get("csv_thousands", None)

    candidates = [
        (cfg_sep, cfg_dec, cfg_ths),
        (";", ",", "."),   # typical EU
        (",", ".", ","),   # typical US
        (";", ".", ","),
        (",", ",", "."),
    ]

    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _detect_csv_format(file_path):
    best = None
    best_score = -1

    for sep, dec, ths in _candidate_csv_formats():
        try:
            preview = pd.read_csv(
                file_path,
                sep=sep,
                decimal=dec,
                thousands=ths,
                comment="#",
                nrows=200,
                engine="c",
                header=None,
                names=REQ + OPT,
                skip_blank_lines=True,
            )
            if preview.empty:
                continue

            req_num = preview[REQ].apply(pd.to_numeric, errors="coerce")
            nonnull = int(req_num.notna().sum().sum())
            plausible = int((req_num["rfsg"].median(skipna=True) > 1e6) and (req_num["usrp"].median(skipna=True) > 1e6))
            score = nonnull + 1000 * plausible

            if score > best_score:
                best_score = score
                best = (sep, dec, ths)
        except Exception:
            continue

    return best




def _coerce_numeric_columns(df):
    numeric_cols = [c for c in (REQ + OPT) if c in df.columns]
    for col in numeric_cols:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue

        s = df[col].astype(str).str.strip()
        parsed = pd.to_numeric(s, errors="coerce")

        if parsed.notna().sum() == 0:
            eu = pd.to_numeric(
                s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                errors="coerce",
            )
            us = pd.to_numeric(
                s.str.replace(",", "", regex=False),
                errors="coerce",
            )
            parsed = eu if eu.notna().sum() >= us.notna().sum() else us

        df[col] = parsed

    return df

def load_dataframe(file_path):
    print("Loading CSV file...")
    start_time = time.perf_counter()

    skip_warning = CONFIG.get("skip_csv_warning", False)

    detected = _detect_csv_format(file_path)
    if detected is None:
        if skip_warning:
            print("⚠️ Could not auto-detect CSV format; returning empty DataFrame.")
            return pd.DataFrame(columns=REQ + OPT)
        raise SystemExit("Aborting due to unreadable CSV format (delimiter/decimal).")

    sep, dec, ths = detected
    cfg_sep = CONFIG.get("csv_delimiter", ";")
    cfg_dec = CONFIG.get("csv_decimal", ",")
    if (sep, dec) != (cfg_sep, cfg_dec):
        print(f"ℹ️ Auto-detected CSV format: delimiter='{sep}' decimal='{dec}' (overriding settings).")
    else:
        print(f"ℹ️ CSV format: delimiter='{sep}' decimal='{dec}'.")

    # --- Dask ---
    if CONFIG.get("use_dask", False):
        try:
            import dask.dataframe as dd
            from dask.diagnostics import ProgressBar
            print("Using Dask for multi-core CSV loading...")
            dtype_map = {col: 'float64' for col in REQ + OPT}
            ddf = dd.read_csv(
                file_path,
                sep=sep,
                decimal=dec,
                thousands=ths,
                comment="#",
                names=REQ + OPT,
                dtype=dtype_map,
                assume_missing=True,
                blocksize=CONFIG.get("dask_blocksize")
            )
            ddf = ddf.dropna(subset=["rfsg", "usrp"]).persist()
            with ProgressBar():
                df = ddf.compute()
            df = _coerce_numeric_columns(df)
            df.dropna(subset=["rfsg", "usrp"], inplace=True)
            print(f"Loaded via Dask in {time.perf_counter() - start_time:.2f}s.")
            return df
        except Exception as e:
            print(f"Dask read failed ({e}), falling back to Pandas.")

    # --- Pandas fallback ---
    desired_time = CONFIG.get("chunk_target_time", 0.2)
    sample_rows = CONFIG.get("sample_chunk_rows", 5000)
    default_chunk = CONFIG.get("default_chunk_size", 50000)
    ram_fraction = CONFIG.get("ram_fraction", 0.2)
    dtype_map = {col: 'float64' for col in REQ + OPT}

    # Estimate chunk size
    try:
        print(f"Estimating performance with {sample_rows} rows...")
        pd.read_csv(
            file_path,
            sep=sep,
            decimal=dec,
            thousands=ths,
            comment="#",
            names=REQ + OPT,
            skip_blank_lines=True,
            nrows=sample_rows,
            dtype=dtype_map,
            engine='c'
        )
        sample_time = time.perf_counter() - start_time
        bytes_count, rows = 0, 0
        with open(file_path, 'rb') as fb:
            while rows < sample_rows:
                line = fb.readline()
                if not line:
                    break
                if not line.startswith(b'#') and line.strip():
                    bytes_count += len(line)
                    rows += 1
        avg_bytes = bytes_count / rows if rows else 1
    except Exception as e:
        print(f"Sample estimation failed ({e}), using default chunk size.")
        sample_time, avg_bytes = None, 1

    if sample_time and sample_time > 0:
        speed = sample_rows / sample_time
        chunk_perf = int(speed * desired_time)
    else:
        chunk_perf = default_chunk

    try:
        import psutil
        avail_ram = psutil.virtual_memory().available
        max_rows_ram = int((avail_ram * ram_fraction) / avg_bytes)
    except:
        max_rows_ram = default_chunk

    chunk = max(
        min(chunk_perf, max_rows_ram, CONFIG.get("max_chunk_size", 200000)),
        CONFIG.get("min_chunk_size", 1000)
    )
    print(f"Final chunk size: {chunk}")

    # Read CSV in chunks, but catch failure on first chunk
    try:
        reader = pd.read_csv(
            file_path,
            sep=sep,
            decimal=dec,
            thousands=ths,
            comment="#",
            names=REQ + OPT,
            skip_blank_lines=True,
            chunksize=chunk,
            iterator=True,
            dtype=dtype_map,
            engine='c'
        )
        first_chunk = next(reader)  # ← catch parse error here
        chunks = [first_chunk]
    except Exception as e:
        print("\n❌ CSV chunk parsing failed.")
        print(f"→ Auto-detected: delimiter='{sep}', decimal='{dec}'")
        print(f"→ Error: {e}")
        if skip_warning:
            print("⚠️ Skipping error due to 'skip_csv_warning': True (data may be corrupted)")
            return pd.DataFrame(columns=REQ + OPT)
        raise SystemExit("Aborting due to unreadable CSV structure.")

    # Progress bar
    sys.stdout.write("[" + "-"*50 + "] 0%")
    sys.stdout.flush()
    try:
        file_size = os.path.getsize(file_path)
        est_rows = file_size / (avg_bytes or 1)
    except:
        est_rows = None

    read = len(first_chunk)
    for part in reader:
        chunks.append(part)
        read += len(part)
        if est_rows:
            pct = min(int(read / est_rows * 100), 99)
            bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
            sys.stdout.write(f"\r[{bar}] {pct}%")
            sys.stdout.flush()
    sys.stdout.write("\r[" + "#" * 50 + "] 100%\n")

    df = pd.concat(chunks, ignore_index=True)
    df = _coerce_numeric_columns(df)
    df.dropna(subset=["rfsg", "usrp"], inplace=True)

    print(f"CSV file loaded in {time.perf_counter() - start_time:.2f}s.")
    return df


def check_warnings(df):
    warnings = []
    for col in REQ:
        if df[col].isna().all():
            warnings.append(f"{col} column is missing or empty")
    for col in OPT:
        if col not in df.columns or df[col].isna().all():
            warnings.append(f"{col} column not available")
    return warnings


def prepare_dataframe(df):
    has_iq = "IQ_MAX_Absolute" in df.columns and not df["IQ_MAX_Absolute"].isna().all()
    if has_iq:
        df["IQ"] = df["IQ_MAX_Absolute"]
    for col in OPT:
        if col not in df.columns:
            df[col] = np.nan
    df["rfsg_ghz"] = df["rfsg"] / 1e9
    df["usrp_ghz"] = df["usrp"] / 1e9
    return df, has_iq


def build_reference_maps(df):
    REF_AMP, REF_USRP = {}, {}
    for cf, g in df.groupby("rfsg_ghz"):
        idx = (g["usrp_ghz"] - cf).abs().idxmin()
        REF_AMP[cf] = g.at[idx, "amp"]
        REF_USRP[cf] = g.at[idx, "usrp_ghz"]
    return REF_AMP, REF_USRP


def get_axis_limits(df):
    return (
        round(df["rfsg_ghz"].min(), 3),
        round(df["rfsg_ghz"].max(), 3),
        round(df["usrp_ghz"].min(), 3),
        round(df["usrp_ghz"].max(), 3)
    )
