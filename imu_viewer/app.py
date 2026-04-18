from __future__ import annotations

import argparse
from pathlib import Path

from PySide6 import QtWidgets

from .constants import DEFAULT_SAMPLE_PERIOD
from .data import build_series, build_x_axis, guess_time_column, read_csv, resolve_y_columns
from .window import ScopeWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display IMU CSV data in an interactive oscilloscope-style PyQtGraph window.",
    )
    parser.add_argument("csv_path", type=Path, help="Path to the CSV file.")
    parser.add_argument(
        "--y",
        nargs="+",
        help="Columns to plot. If omitted, all numeric columns except the detected time column are used.",
    )
    parser.add_argument(
        "--time-column",
        help="Name of the column used as the X axis. If omitted, the script auto-detects time-like columns.",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        help="Use sample rate in Hz to build a time axis when the CSV has no time column.",
    )
    parser.add_argument(
        "--sample-period",
        type=float,
        help=f"Use sample period in seconds when the CSV has no time column. Default is {DEFAULT_SAMPLE_PERIOD} s.",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Draw each selected channel in its own stacked plot instead of a single shared plot.",
    )
    parser.add_argument(
        "--highpass-cutoff",
        type=float,
        help="Initialize the GUI high-pass filter control with this cutoff frequency in Hz.",
    )
    parser.add_argument(
        "--lowpass-cutoff",
        type=float,
        help="Initialize the GUI low-pass filter control with this cutoff frequency in Hz.",
    )
    parser.add_argument(
        "--title",
        help="Optional window title.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.sample_rate is not None and args.sample_period is not None:
        raise ValueError("Use either --sample-rate or --sample-period, not both.")
    if args.highpass_cutoff is not None and args.highpass_cutoff <= 0:
        raise ValueError("--highpass-cutoff must be positive.")
    if args.lowpass_cutoff is not None and args.lowpass_cutoff <= 0:
        raise ValueError("--lowpass-cutoff must be positive.")

    headers, rows = read_csv(args.csv_path)
    y_columns = resolve_y_columns(headers, rows, args.y)
    time_column = args.time_column or guess_time_column(headers)
    x_values, x_label, using_csv_time_axis = build_x_axis(rows, time_column, args.sample_rate, args.sample_period)

    if not y_columns:
        raise ValueError("No numeric IMU columns were found to plot.")

    series_map = {column: build_series(rows, x_values, column) for column in y_columns}

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = ScopeWindow(
        csv_path=args.csv_path,
        rows=rows,
        y_columns=y_columns,
        time_column=time_column,
        x_values=x_values,
        x_label=x_label,
        series_map=series_map,
        split=args.split,
        title=args.title,
        using_csv_time_axis=using_csv_time_axis,
        initial_sample_rate_hz=args.sample_rate,
        initial_sample_period_s=args.sample_period,
        initial_highpass_cutoff_hz=args.highpass_cutoff,
        initial_lowpass_cutoff_hz=args.lowpass_cutoff,
    )
    window.show()
    app.exec()
