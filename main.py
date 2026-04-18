from __future__ import annotations

import argparse
import bisect
import csv
from pathlib import Path
from typing import Callable

import pyqtgraph as pg
from pyqtgraph import functions as fn
from PySide6 import QtCore, QtGui, QtWidgets


TIME_COLUMN_CANDIDATES = (
    "time",
    "timestamp",
    "t",
    "ms",
    "millis",
    "millisecond",
    "millisec",
    "us",
    "micros",
    "microsecond",
    "seconds",
    "sec",
)

PLOT_COLORS = (
    "#5B84B1",
    "#7AA6A1",
    "#D9A066",
    "#C97B63",
    "#B07AA1",
    "#7B8C99",
    "#8AAE92",
    "#8C7AA9",
)

CURSOR_COLORS = {
    "A": "#C08A4D",
    "B": "#B46A7A",
}

APP_BACKGROUND = "#F4F1EA"
PANEL_BACKGROUND = "#ECE7DE"
PLOT_BACKGROUND = "#FBF9F5"
TEXT_PRIMARY = "#3E4B53"
TEXT_SECONDARY = "#66757F"
AXIS_COLOR = "#A2AEB6"
AXIS_TEXT = "#516069"
TITLE_COLOR = "#2F3D45"
FORE_COLOR = "#65757E"
HOVER_LINE_COLOR = "#96A6AF"
DEFAULT_SAMPLE_PERIOD = 0.01


def normalize_name(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum())


def guess_time_column(headers: list[str]) -> str | None:
    normalized = {normalize_name(header): header for header in headers}
    for candidate in TIME_COLUMN_CANDIDATES:
        header = normalized.get(normalize_name(candidate))
        if header:
            return header
    return None


def read_csv(csv_path: Path) -> tuple[list[str], list[dict[str, float]]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("CSV does not contain a header row.")

        headers = [header.strip() for header in reader.fieldnames]
        rows: list[dict[str, float]] = []

        for raw_row in reader:
            parsed: dict[str, float] = {}
            for header in headers:
                raw_value = (raw_row.get(header) or "").strip()
                if raw_value == "":
                    continue
                try:
                    parsed[header] = float(raw_value)
                except ValueError:
                    continue
            if parsed:
                rows.append(parsed)

    if not rows:
        raise ValueError("CSV does not contain any numeric rows.")

    return headers, rows


def resolve_y_columns(headers: list[str], rows: list[dict[str, float]], requested: list[str] | None) -> list[str]:
    numeric_headers = [header for header in headers if any(header in row for row in rows)]

    if requested:
        missing = [column for column in requested if column not in numeric_headers]
        if missing:
            available = ", ".join(numeric_headers)
            raise ValueError(f"Unknown column(s): {', '.join(missing)}. Available numeric columns: {available}")
        return requested

    time_column = guess_time_column(numeric_headers)
    return [header for header in numeric_headers if header != time_column]


def build_x_axis(
    rows: list[dict[str, float]],
    time_column: str | None,
    sample_rate: float | None,
    sample_period: float | None,
) -> tuple[list[float], str, bool]:
    if time_column:
        x_values = [row.get(time_column) for row in rows]
        valid_x = [value for value in x_values if value is not None]
        if len(valid_x) == len(rows):
            axis_label = time_column
            normalized = normalize_name(time_column)
            if normalized in {"ms", "millis", "millisecond", "millisec"}:
                axis_label = f"{time_column} (ms)"
            elif normalized in {"us", "micros", "microsecond"}:
                axis_label = f"{time_column} (us)"
            elif normalized in {"time", "timestamp", "t", "seconds", "sec"}:
                axis_label = f"{time_column} (s)"
            return valid_x, axis_label, True

    effective_period = sample_period
    if effective_period is None:
        if sample_rate and sample_rate > 0:
            effective_period = 1.0 / sample_rate
        else:
            effective_period = DEFAULT_SAMPLE_PERIOD

    if effective_period <= 0:
        raise ValueError("Sample period must be positive.")

    return [index * effective_period for index in range(len(rows))], "Time (s)", False


def build_series(rows: list[dict[str, float]], x_values: list[float], column: str) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for index, row in enumerate(rows):
        value = row.get(column)
        if value is None:
            continue
        xs.append(x_values[index])
        ys.append(value)
    return xs, ys


def x_axis_scale_to_seconds(x_label: str) -> float | None:
    if "(us)" in x_label:
        return 1e-6
    if "(ms)" in x_label:
        return 1e-3
    if "(s)" in x_label:
        return 1.0
    return None


def estimate_sample_period_seconds(x_values: list[float], x_label: str) -> float | None:
    if len(x_values) < 2:
        return None

    scale_to_seconds = x_axis_scale_to_seconds(x_label)
    if scale_to_seconds is None:
        return None

    deltas = [x_values[index] - x_values[index - 1] for index in range(1, len(x_values))]
    positive_deltas = [delta * scale_to_seconds for delta in deltas if delta > 0]
    if not positive_deltas:
        return None
    return sum(positive_deltas) / len(positive_deltas)


def low_pass_series(xs: list[float], ys: list[float], x_label: str, cutoff_hz: float) -> tuple[list[float], list[float]]:
    if cutoff_hz <= 0:
        raise ValueError("Low-pass cutoff must be positive.")
    if len(xs) != len(ys):
        raise ValueError("X and Y series lengths do not match.")
    if len(ys) < 2:
        return xs, ys

    scale_to_seconds = x_axis_scale_to_seconds(x_label)
    if scale_to_seconds is None:
        raise ValueError("Cannot apply low-pass filter because the X axis unit is unknown.")

    rc = 1.0 / (2.0 * 3.141592653589793 * cutoff_hz)
    filtered = [ys[0]]

    for index in range(1, len(ys)):
        dt = (xs[index] - xs[index - 1]) * scale_to_seconds
        if dt <= 0:
            filtered.append(filtered[-1])
            continue
        alpha = dt / (rc + dt)
        filtered.append(filtered[-1] + alpha * (ys[index] - filtered[-1]))

    return xs, filtered


def high_pass_series(xs: list[float], ys: list[float], x_label: str, cutoff_hz: float) -> tuple[list[float], list[float]]:
    if cutoff_hz <= 0:
        raise ValueError("High-pass cutoff must be positive.")
    if len(xs) != len(ys):
        raise ValueError("X and Y series lengths do not match.")
    if len(ys) < 2:
        return xs, ys

    scale_to_seconds = x_axis_scale_to_seconds(x_label)
    if scale_to_seconds is None:
        raise ValueError("Cannot apply high-pass filter because the X axis unit is unknown.")

    rc = 1.0 / (2.0 * 3.141592653589793 * cutoff_hz)
    filtered = [0.0]

    for index in range(1, len(ys)):
        dt = (xs[index] - xs[index - 1]) * scale_to_seconds
        if dt <= 0:
            filtered.append(filtered[-1])
            continue
        alpha = rc / (rc + dt)
        filtered.append(alpha * (filtered[-1] + ys[index] - ys[index - 1]))

    return xs, filtered


def apply_filter_chain(
    xs: list[float],
    ys: list[float],
    x_label: str,
    highpass_cutoff_hz: float | None,
    lowpass_cutoff_hz: float | None,
) -> tuple[list[float], list[float]]:
    current_xs = xs
    current_ys = ys

    if highpass_cutoff_hz is not None:
        current_xs, current_ys = high_pass_series(current_xs, current_ys, x_label, highpass_cutoff_hz)
    if lowpass_cutoff_hz is not None:
        current_xs, current_ys = low_pass_series(current_xs, current_ys, x_label, lowpass_cutoff_hz)

    return current_xs, current_ys


def make_info_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setWordWrap(False)
    label.setStyleSheet(
        f"QLabel {{ color: {TEXT_PRIMARY}; background: {PANEL_BACKGROUND}; padding: 4px 8px; border: 1px solid #D9D2C7; font-family: Consolas, monospace; font-size: 12px; font-weight: 600; }}"
    )
    return label


class ScopeWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        csv_path: Path,
        rows: list[dict[str, float]],
        y_columns: list[str],
        time_column: str | None,
        x_values: list[float],
        x_label: str,
        series_map: dict[str, tuple[list[float], list[float]]],
        split: bool,
        title: str | None,
        using_csv_time_axis: bool,
        initial_sample_rate_hz: float | None,
        initial_sample_period_s: float | None,
        initial_highpass_cutoff_hz: float | None,
        initial_lowpass_cutoff_hz: float | None,
    ) -> None:
        super().__init__()
        self.csv_path = csv_path
        self.rows = rows
        self.y_columns = y_columns
        self.time_column = time_column
        self.x_values = x_values
        self.x_label = x_label
        self.using_csv_time_axis = using_csv_time_axis
        self.sample_period_s = (
            initial_sample_period_s
            if initial_sample_period_s is not None
            else (1.0 / initial_sample_rate_hz if initial_sample_rate_hz and initial_sample_rate_hz > 0 else DEFAULT_SAMPLE_PERIOD)
        )
        self.sample_rate_hz = 1.0 / self.sample_period_s
        if self.using_csv_time_axis:
            estimated_sample_period_s = estimate_sample_period_seconds(self.x_values, self.x_label)
            if estimated_sample_period_s is not None and estimated_sample_period_s > 0:
                self.sample_period_s = estimated_sample_period_s
                self.sample_rate_hz = 1.0 / estimated_sample_period_s
        self.raw_series_map = series_map
        self.processed_series_map: dict[str, tuple[list[float], list[float]]] | None = None
        self.processed_signature: tuple[float | None, float | None] | None = None
        self.highpass_cutoff_hz = initial_highpass_cutoff_hz if initial_highpass_cutoff_hz is not None else 0.5
        self.highpass_enabled = initial_highpass_cutoff_hz is not None
        self.lowpass_cutoff_hz = initial_lowpass_cutoff_hz if initial_lowpass_cutoff_hz is not None else 5.0
        self.lowpass_enabled = initial_lowpass_cutoff_hz is not None
        self.series_map = self._get_active_series_map()
        self.split = split
        self.base_title = title or f"IMU Scope View - {csv_path.name}"
        self.plot_widgets: list[pg.PlotWidget] = []
        self.plots: list[pg.PlotItem] = []
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.crosshairs: list[pg.InfiniteLine] = []
        self.cursor_lines: dict[str, list[pg.InfiniteLine]] = {"A": [], "B": []}
        self.cursor_positions: dict[str, float] = {}
        self._syncing_cursor = False
        self._syncing_time_controls = False

        self._update_window_title()
        self.resize(1500, 900)

        self.measure_label = make_info_label("Cursors: initializing...")
        self.cursor_values_label = make_info_label("A/B values: initializing...")

        status_bar = QtWidgets.QStatusBar()
        status_bar.setStyleSheet(
            f"QStatusBar {{ color: {TEXT_SECONDARY}; background: {PANEL_BACKGROUND}; border-top: 1px solid #D9D2C7; font-family: Consolas, monospace; font-size: 13px; font-weight: 600; }}"
        )
        self.setStatusBar(status_bar)
        self.statusBar().showMessage(
            "Wheel: zoom | Left drag: box zoom | Right drag: pan | Middle click: reset | Drag cursors A/B to measure | R: reset view"
        )

        container = QtWidgets.QWidget()
        container.setStyleSheet(f"background: {APP_BACKGROUND};")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.plot_layout = layout
        self._build_top_controls(layout)
        layout.addWidget(self.measure_label)
        layout.addWidget(self.cursor_values_label)
        self.setCentralWidget(container)

        self._build_plots(x_label)
        self._install_measurement_cursors()
        self._install_crosshair()

    def _build_top_controls(self, layout: QtWidgets.QVBoxLayout) -> None:
        controls = QtWidgets.QFrame()
        controls.setObjectName("controlBar")
        controls.setStyleSheet(
            f"QFrame#controlBar {{ background: {PANEL_BACKGROUND}; border: 1px solid #D9D2C7; }}"
            f" QFrame#controlBlock {{ background: {APP_BACKGROUND}; border: 1px solid #D4CEC3; border-radius: 4px; }}"
            f" QLabel {{ color: {TEXT_PRIMARY}; font-family: Consolas, monospace; font-size: 12px; font-weight: 600; border: none; }}"
            f" QCheckBox {{ color: {TEXT_PRIMARY}; font-family: Consolas, monospace; font-size: 12px; font-weight: 600; border: none; spacing: 4px; }}"
            f" QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #A89F92; border-radius: 3px; background: #FFFDF9; }}"
            f" QCheckBox::indicator:hover {{ border: 1px solid #7E7468; background: #F7F2EA; }}"
            f" QCheckBox::indicator:checked {{ background: #5B84B1; border: 1px solid #456789; }}"
            f" QCheckBox::indicator:checked:hover {{ background: #4F779F; border: 1px solid #3F607F; }}"
            f" QDoubleSpinBox {{ color: {TEXT_PRIMARY}; background: {PLOT_BACKGROUND}; padding: 2px 4px; border: 1px solid #C9C2B7; font-family: Consolas, monospace; font-size: 12px; min-height: 22px; }}"
            f" QPushButton {{ color: {TEXT_PRIMARY}; background: {PLOT_BACKGROUND}; border: 1px solid #C9C2B7; font-family: Consolas, monospace; font-size: 12px; font-weight: 700; min-width: 22px; min-height: 22px; padding: 0; }}"
            f" QPushButton:hover {{ background: #E2DDD4; }}"
            f" QPushButton:pressed {{ background: #D6D0C6; }}"
        )
        control_layout = QtWidgets.QHBoxLayout(controls)
        control_layout.setContentsMargins(8, 5, 8, 5)
        control_layout.setSpacing(6)

        source_label = QtWidgets.QLabel("X")
        self.sample_rate_spin = QtWidgets.QDoubleSpinBox()
        self.sample_rate_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.sample_rate_spin.setDecimals(2)
        self.sample_rate_spin.setRange(0.001, 1_000_000.0)
        self.sample_rate_spin.setSingleStep(1.0)
        self.sample_rate_spin.setMaximumWidth(92)
        self.sample_rate_spin.setValue(self.sample_rate_hz)
        self.sample_rate_spin.valueChanged.connect(self._on_sample_rate_changed)
        self.sample_rate_down_button = self._make_step_button("-", self.sample_rate_spin, -1)
        self.sample_rate_up_button = self._make_step_button("+", self.sample_rate_spin, 1)

        self.highpass_checkbox = QtWidgets.QCheckBox("HP")
        self.highpass_checkbox.setChecked(self.highpass_enabled)
        self.highpass_checkbox.toggled.connect(self._on_highpass_toggled)

        self.highpass_cutoff_spin = QtWidgets.QDoubleSpinBox()
        self.highpass_cutoff_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.highpass_cutoff_spin.setDecimals(2)
        self.highpass_cutoff_spin.setRange(0.01, 10000.0)
        self.highpass_cutoff_spin.setSingleStep(0.5)
        self.highpass_cutoff_spin.setMaximumWidth(78)
        self.highpass_cutoff_spin.setValue(self.highpass_cutoff_hz)
        self.highpass_cutoff_spin.valueChanged.connect(self._on_highpass_cutoff_changed)
        self.highpass_down_button = self._make_step_button("-", self.highpass_cutoff_spin, -1)
        self.highpass_up_button = self._make_step_button("+", self.highpass_cutoff_spin, 1)

        self.lowpass_checkbox = QtWidgets.QCheckBox("LP")
        self.lowpass_checkbox.setChecked(self.lowpass_enabled)
        self.lowpass_checkbox.toggled.connect(self._on_lowpass_toggled)

        self.lowpass_cutoff_spin = QtWidgets.QDoubleSpinBox()
        self.lowpass_cutoff_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.lowpass_cutoff_spin.setDecimals(2)
        self.lowpass_cutoff_spin.setRange(0.01, 10000.0)
        self.lowpass_cutoff_spin.setSingleStep(0.5)
        self.lowpass_cutoff_spin.setMaximumWidth(78)
        self.lowpass_cutoff_spin.setValue(self.lowpass_cutoff_hz)
        self.lowpass_cutoff_spin.valueChanged.connect(self._on_lowpass_cutoff_changed)
        self.lowpass_down_button = self._make_step_button("-", self.lowpass_cutoff_spin, -1)
        self.lowpass_up_button = self._make_step_button("+", self.lowpass_cutoff_spin, 1)

        self.compact_status_label = QtWidgets.QLabel()
        hz_label_1 = QtWidgets.QLabel("Hz")
        hz_label_2 = QtWidgets.QLabel("Hz")
        hz_label_3 = QtWidgets.QLabel("Hz")

        hp_block = self._make_control_block(
            self.highpass_checkbox,
            self.highpass_down_button,
            self.highpass_cutoff_spin,
            self.highpass_up_button,
            hz_label_1,
        )
        lp_block = self._make_control_block(
            self.lowpass_checkbox,
            self.lowpass_down_button,
            self.lowpass_cutoff_spin,
            self.lowpass_up_button,
            hz_label_2,
        )
        x_block = self._make_control_block(
            source_label,
            self.sample_rate_down_button,
            self.sample_rate_spin,
            self.sample_rate_up_button,
            hz_label_3,
        )
        status_block = self._make_control_block(self.compact_status_label)

        control_layout.addWidget(hp_block)
        control_layout.addWidget(lp_block)
        control_layout.addWidget(x_block)
        control_layout.addWidget(status_block, stretch=1)
        layout.addWidget(controls)
        self._sync_time_control_state()
        self._sync_filter_control_state()
        self._update_compact_status_label()

    @staticmethod
    def _make_control_block(*widgets: QtWidgets.QWidget) -> QtWidgets.QFrame:
        block = QtWidgets.QFrame()
        block.setObjectName("controlBlock")
        block_layout = QtWidgets.QHBoxLayout(block)
        block_layout.setContentsMargins(6, 4, 6, 4)
        block_layout.setSpacing(5)
        for widget in widgets:
            block_layout.addWidget(widget)
        return block

    @staticmethod
    def _make_step_button(label: str, spinbox: QtWidgets.QDoubleSpinBox, direction: int) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(label)
        button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda: spinbox.stepBy(direction))
        return button

    def _build_plots(self, x_label: str) -> None:
        pg.setConfigOptions(antialias=False, background=PLOT_BACKGROUND, foreground=FORE_COLOR, leftButtonPan=False)

        if not self.split:
            plot = self._add_plot_widget(title=self.windowTitle())
            plot.setLabel("bottom", x_label)
            plot.setLabel("left", "Value")
            legend = plot.addLegend(offset=(10, 10), labelTextColor=TEXT_PRIMARY)
            for index, (column, (xs, ys)) in enumerate(self.series_map.items()):
                curve = plot.plot(
                    xs,
                    ys,
                    pen=pg.mkPen(PLOT_COLORS[index % len(PLOT_COLORS)], width=2.4),
                    clipToView=True,
                    autoDownsample=True,
                    downsampleMethod="peak",
                )
                legend.addItem(curve, column)
                self.curves[column] = curve
            self.plots.append(plot)
            return

        for index, (column, (xs, ys)) in enumerate(self.series_map.items()):
            plot = self._add_plot_widget(title=column if index == 0 else None)
            plot.setLabel("left", column)
            if index == len(self.series_map) - 1:
                plot.setLabel("bottom", x_label)
            curve = plot.plot(
                xs,
                ys,
                pen=pg.mkPen(PLOT_COLORS[index % len(PLOT_COLORS)], width=2.4),
                clipToView=True,
                autoDownsample=True,
                downsampleMethod="peak",
            )
            self.curves[column] = curve
            if self.plots:
                plot.setXLink(self.plots[0])
            self.plots.append(plot)

    def _filter_signature(self) -> tuple[float | None, float | None]:
        return (
            self.highpass_cutoff_hz if self.highpass_enabled else None,
            self.lowpass_cutoff_hz if self.lowpass_enabled else None,
        )

    def _get_processed_series_map(self) -> dict[str, tuple[list[float], list[float]]]:
        signature = self._filter_signature()
        if self.processed_series_map is not None and self.processed_signature == signature:
            return self.processed_series_map

        self.processed_series_map = {
            column: apply_filter_chain(xs, ys, self.x_label, signature[0], signature[1])
            for column, (xs, ys) in self.raw_series_map.items()
        }
        self.processed_signature = signature
        return self.processed_series_map

    def _get_active_series_map(self) -> dict[str, tuple[list[float], list[float]]]:
        if self.highpass_enabled or self.lowpass_enabled:
            return self._get_processed_series_map()
        return self.raw_series_map

    def _sync_filter_control_state(self) -> None:
        self.highpass_cutoff_spin.setEnabled(self.highpass_enabled)
        self.highpass_down_button.setEnabled(self.highpass_enabled)
        self.highpass_up_button.setEnabled(self.highpass_enabled)
        self.lowpass_cutoff_spin.setEnabled(self.lowpass_enabled)
        self.lowpass_down_button.setEnabled(self.lowpass_enabled)
        self.lowpass_up_button.setEnabled(self.lowpass_enabled)

    def _sync_time_control_state(self) -> None:
        enabled = not self.using_csv_time_axis
        self.sample_rate_spin.setEnabled(enabled)
        self.sample_rate_down_button.setEnabled(enabled)
        self.sample_rate_up_button.setEnabled(enabled)

    def _update_time_controls(self) -> None:
        self._syncing_time_controls = True
        try:
            self.sample_rate_spin.setValue(self.sample_rate_hz)
        finally:
            self._syncing_time_controls = False

    def _rebuild_time_axis(self) -> None:
        old_x_values = list(self.x_values)
        old_cursor_positions = dict(self.cursor_positions)
        self.x_values, self.x_label, self.using_csv_time_axis = build_x_axis(
            self.rows,
            self.time_column,
            self.sample_rate_hz,
            self.sample_period_s,
        )
        self.raw_series_map = {column: build_series(self.rows, self.x_values, column) for column in self.y_columns}
        self.processed_series_map = None
        self.processed_signature = None
        self._sync_time_control_state()
        self._refresh_series_display()
        self._restore_cursor_positions(old_x_values, old_cursor_positions)

    def _restore_cursor_positions(self, old_x_values: list[float], old_cursor_positions: dict[str, float]) -> None:
        if not old_x_values or not self.x_values or not old_cursor_positions:
            return

        self._syncing_cursor = True
        try:
            for cursor_name, previous_x in old_cursor_positions.items():
                old_index = self._nearest_index(old_x_values, previous_x)
                new_index = min(old_index, len(self.x_values) - 1)
                new_x = self.x_values[new_index]
                self.cursor_positions[cursor_name] = new_x
                for line in self.cursor_lines[cursor_name]:
                    line.setValue(new_x)
        finally:
            self._syncing_cursor = False

        self._update_measurements()

    def _on_sample_rate_changed(self, value: float) -> None:
        if self._syncing_time_controls or value <= 0:
            return
        self.sample_rate_hz = value
        self.sample_period_s = 1.0 / value
        self._update_time_controls()
        if not self.using_csv_time_axis:
            self._rebuild_time_axis()

    def _timebase_status_label(self) -> str:
        if self.using_csv_time_axis:
            return f"X:{self.time_column or 'CSV'}"
        return f"X:{self.sample_rate_hz:.6g}Hz"

    def _update_compact_status_label(self) -> None:
        parts = [self._timebase_status_label(), self._filter_mode_label() or "Raw"]
        if self.highpass_enabled and self.lowpass_enabled and self.highpass_cutoff_hz >= self.lowpass_cutoff_hz:
            parts.append("HP>=LP")
        self.compact_status_label.setText(" | ".join(parts))

    def _filter_mode_label(self) -> str | None:
        if self.highpass_enabled and self.lowpass_enabled:
            return f"BPF {self.highpass_cutoff_hz:g}-{self.lowpass_cutoff_hz:g} Hz"
        if self.highpass_enabled:
            return f"HPF {self.highpass_cutoff_hz:g} Hz"
        if self.lowpass_enabled:
            return f"LPF {self.lowpass_cutoff_hz:g} Hz"
        return None

    def _update_window_title(self) -> None:
        mode_label = self._filter_mode_label()
        if mode_label is not None:
            self.setWindowTitle(f"{self.base_title} [{mode_label}]")
            return
        self.setWindowTitle(self.base_title)

    def _refresh_series_display(self) -> None:
        self.series_map = self._get_active_series_map()
        for column, curve in self.curves.items():
            xs, ys = self.series_map[column]
            curve.setData(xs, ys)
        if not self.split and self.plots:
            self.plots[0].setTitle(self.windowTitle(), color=TITLE_COLOR, size="15pt")
        self._update_compact_status_label()
        self._update_measurements()

    def _on_highpass_toggled(self, checked: bool) -> None:
        self.highpass_enabled = checked
        self._sync_filter_control_state()
        self._update_window_title()
        self._refresh_series_display()

    def _on_highpass_cutoff_changed(self, value: float) -> None:
        self.highpass_cutoff_hz = value
        if self.highpass_enabled:
            self._update_window_title()
            self._refresh_series_display()

    def _on_lowpass_toggled(self, checked: bool) -> None:
        self.lowpass_enabled = checked
        self._sync_filter_control_state()
        self._update_window_title()
        self._refresh_series_display()

    def _on_lowpass_cutoff_changed(self, value: float) -> None:
        self.lowpass_cutoff_hz = value
        if self.lowpass_enabled:
            self._update_window_title()
            self._refresh_series_display()

    def _add_plot_widget(self, title: str | None = None) -> pg.PlotItem:
        plot_widget = ScopePlotWidget(reset_callback=self._reset_all_views)
        plot_widget.setBackground(PLOT_BACKGROUND)
        self.plot_layout.addWidget(plot_widget, stretch=1)
        self.plot_widgets.append(plot_widget)

        plot = plot_widget.getPlotItem()
        if title:
            plot.setTitle(title, color=TITLE_COLOR, size="15pt")
        plot.showGrid(x=True, y=True, alpha=0.22)
        plot.setMenuEnabled(True)
        plot.setMouseEnabled(x=True, y=True)
        plot.setDownsampling(auto=True, mode="peak")
        plot.setClipToView(True)
        plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        plot.getAxis("left").setStyle(tickTextOffset=10)
        plot.getAxis("bottom").setStyle(tickTextOffset=10)
        axis_font = QtGui.QFont("Consolas", 10)
        axis_font.setBold(True)
        plot.getAxis("left").tickFont = axis_font
        plot.getAxis("bottom").tickFont = axis_font
        plot.getAxis("left").setTextPen(AXIS_TEXT)
        plot.getAxis("bottom").setTextPen(AXIS_TEXT)
        plot.getAxis("left").setPen(pg.mkPen(AXIS_COLOR, width=1.8))
        plot.getAxis("bottom").setPen(pg.mkPen(AXIS_COLOR, width=1.8))
        return plot

    def _reset_all_views(self) -> None:
        for plot in self.plots:
            plot.enableAutoRange()
            plot.autoRange()

    def _install_measurement_cursors(self) -> None:
        if not self.x_values or not self.plots:
            return

        left_index = max(0, len(self.x_values) // 4)
        right_index = min(len(self.x_values) - 1, (len(self.x_values) * 3) // 4)
        self.cursor_positions = {
            "A": self.x_values[left_index],
            "B": self.x_values[right_index],
        }

        for plot in self.plots:
            for name in ("A", "B"):
                line = pg.InfiniteLine(
                    pos=self.cursor_positions[name],
                    angle=90,
                    movable=True,
                    pen=pg.mkPen(CURSOR_COLORS[name], width=2.8),
                    label=name,
                    labelOpts={"position": 0.05, "color": CURSOR_COLORS[name], "fill": (0, 0, 0, 0)},
                )
                plot.addItem(line, ignoreBounds=True)
                line.sigPositionChanged.connect(
                    lambda *_, cursor_name=name, cursor_line=line: self._on_cursor_moved(cursor_name, cursor_line)
                )
                self.cursor_lines[name].append(line)

        self._update_measurements()

    def _on_cursor_moved(self, cursor_name: str, moved_line: pg.InfiniteLine) -> None:
        if self._syncing_cursor:
            return

        snapped_x = self.x_values[self._nearest_index(self.x_values, moved_line.value())]
        self._syncing_cursor = True
        try:
            self.cursor_positions[cursor_name] = snapped_x
            for line in self.cursor_lines[cursor_name]:
                if abs(line.value() - snapped_x) > 1e-12:
                    line.setValue(snapped_x)
        finally:
            self._syncing_cursor = False

        self._update_measurements()

    def _install_crosshair(self) -> None:
        if not self.x_values:
            return

        for plot in self.plots:
            line = pg.InfiniteLine(
                angle=90,
                movable=False,
                pen=pg.mkPen(HOVER_LINE_COLOR, width=1.8, style=QtCore.Qt.DashLine),
            )
            plot.addItem(line, ignoreBounds=True)
            self.crosshairs.append(line)
        for plot_widget, plot in zip(self.plot_widgets, self.plots):
            plot_widget.scene().sigMouseMoved.connect(
                lambda pos, current_plot=plot: self._on_mouse_moved(current_plot, pos)
            )

    def _on_mouse_moved(self, plot: pg.PlotItem, pos: object) -> None:
        view_box = plot.getViewBox()
        if not plot.sceneBoundingRect().contains(pos):
            return

        mouse_point = view_box.mapSceneToView(pos)
        x_value = mouse_point.x()
        nearest_index = self._nearest_index(self.x_values, x_value)
        snapped_x = self.x_values[nearest_index]

        for crosshair in self.crosshairs:
            crosshair.setPos(snapped_x)

        parts = [f"Hover x={snapped_x:.6g}"]
        for column, (xs, ys) in self.series_map.items():
            if not xs:
                continue
            series_index = self._nearest_index(xs, snapped_x)
            parts.append(f"{column}={ys[series_index]:.6g}")
        self.statusBar().showMessage(" | ".join(parts))

    def _update_measurements(self) -> None:
        if not self.cursor_positions:
            return

        xa = self.cursor_positions["A"]
        xb = self.cursor_positions["B"]
        dx = xb - xa
        abs_dx = abs(dx)

        dx_seconds = self._x_delta_to_seconds(abs_dx)
        if dx_seconds is not None and dx_seconds > 0:
            period_text = self._format_seconds(dx_seconds)
            freq_text = self._format_frequency(1.0 / dx_seconds)
        else:
            period_text = "n/a"
            freq_text = "n/a"

        self.measure_label.setText(
            f"Cursor A={xa:.6g} | Cursor B={xb:.6g} | Δx={abs_dx:.6g} | Period={period_text} | Freq={freq_text}"
        )

        cursor_value_parts: list[str] = []
        for cursor_name, x_value in (("A", xa), ("B", xb)):
            values = [f"{cursor_name}@{x_value:.6g}"]
            for column, (xs, ys) in self.series_map.items():
                if not xs:
                    continue
                idx = self._nearest_index(xs, x_value)
                values.append(f"{column}={ys[idx]:.6g}")
            cursor_value_parts.append(" | ".join(values))
        self.cursor_values_label.setText("    ||    ".join(cursor_value_parts))

    def _x_delta_to_seconds(self, delta: float) -> float | None:
        if delta <= 0:
            return None

        if "(us)" in self.x_label:
            return delta * 1e-6
        if "(ms)" in self.x_label:
            return delta * 1e-3
        if "(s)" in self.x_label:
            return delta
        return None

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        if seconds >= 1.0:
            return f"{seconds:.6g} s"
        if seconds >= 1e-3:
            return f"{seconds * 1e3:.6g} ms"
        if seconds >= 1e-6:
            return f"{seconds * 1e6:.6g} us"
        return f"{seconds * 1e9:.6g} ns"

    @staticmethod
    def _format_frequency(hz: float) -> str:
        if hz >= 1e6:
            return f"{hz / 1e6:.6g} MHz"
        if hz >= 1e3:
            return f"{hz / 1e3:.6g} kHz"
        return f"{hz:.6g} Hz"

    @staticmethod
    def _nearest_index(values: list[float], target: float) -> int:
        insert_pos = bisect.bisect_left(values, target)
        if insert_pos <= 0:
            return 0
        if insert_pos >= len(values):
            return len(values) - 1
        before = values[insert_pos - 1]
        after = values[insert_pos]
        if abs(target - before) <= abs(after - target):
            return insert_pos - 1
        return insert_pos

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_R:
            self._reset_all_views()
            return
        super().keyPressEvent(event)


class ScopeViewBox(pg.ViewBox):
    def __init__(self, reset_callback: Callable[[], None] | None = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reset_callback = reset_callback
        self.setMouseMode(pg.ViewBox.RectMode)

    def mouseClickEvent(self, ev) -> None:
        if ev.button() == QtCore.Qt.MouseButton.MiddleButton:
            ev.accept()
            if self._reset_callback is not None:
                self._reset_callback()
            else:
                self.enableAutoRange()
                self.autoRange()
            return
        super().mouseClickEvent(ev)

    def mouseDragEvent(self, ev, axis=None) -> None:
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            ev.accept()

            pos = ev.pos()
            last_pos = ev.lastPos()
            dif = (pos - last_pos) * -1

            mouse_enabled = [1.0 if enabled else 0.0 for enabled in self.state["mouseEnabled"]]
            if axis is not None:
                mouse_enabled[1 - axis] = 0.0

            tr = self.childGroup.transform()
            tr = fn.invertQTransform(tr)
            tr = tr.map(dif) - tr.map(pg.Point(0, 0))

            x = tr.x() if mouse_enabled[0] else None
            y = tr.y() if mouse_enabled[1] else None

            self._resetTarget()
            if x is not None or y is not None:
                self.translateBy(x=x, y=y)
            self.sigRangeChangedManually.emit(self.state["mouseEnabled"])
            return

        super().mouseDragEvent(ev, axis=axis)


class ScopePlotWidget(pg.PlotWidget):
    def __init__(self, reset_callback: Callable[[], None] | None = None, *args, **kwargs) -> None:
        kwargs.setdefault("viewBox", ScopeViewBox(reset_callback=reset_callback))
        super().__init__(*args, **kwargs)

    def autoRangeEnabled(self) -> tuple[bool, bool]:
        return self.plotItem.vb.autoRangeEnabled()


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


if __name__ == "__main__":
    main()
