from __future__ import annotations

import csv
from pathlib import Path

from .constants import DEFAULT_SAMPLE_PERIOD, TIME_COLUMN_CANDIDATES


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
