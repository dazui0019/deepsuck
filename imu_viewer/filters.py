from __future__ import annotations

from .data import x_axis_scale_to_seconds


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
