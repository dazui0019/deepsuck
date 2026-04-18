## IMU CSV Viewer

Use `main.py` to display IMU CSV data in an oscilloscope-like interactive window powered by PyQtGraph.

Examples:

```bash
uv run python main.py data.csv
uv run python main.py data.csv --y ax ay az
uv run python main.py data.csv --sample-rate 100
uv run python main.py data.csv --sample-period 0.005
uv run python main.py data.csv --split
uv run python main.py data.csv --highpass-cutoff 0.5
uv run python main.py data.csv --lowpass-cutoff 5
uv run python main.py data.csv --highpass-cutoff 0.5 --lowpass-cutoff 5
```

Behavior:

- If the CSV has a time-like column such as `time`, `timestamp`, `ms`, or `micros`, it is used as the X axis automatically.
- If there is no time column, the script generates a time axis automatically.
- By default, the generated sample period is `0.01 s`.
- You can override the generated time base with `--sample-period` or `--sample-rate`.
- The window exposes a sample rate control for generated time axes, so you can retune the X axis without restarting.
- Without `--y`, the script plots all numeric columns except the detected time column.
- By default, all selected channels are overlaid in one plot area. Use `--split` if you want one stacked plot per channel.
- `--highpass-cutoff <Hz>` initializes the GUI high-pass filter control at that cutoff and starts with high-pass enabled.
- `--lowpass-cutoff <Hz>` initializes the GUI low-pass filter control at that cutoff and starts with filtering enabled.
- The window includes high-pass and low-pass filter checkboxes, so you can switch among raw, HPF, LPF, and band-pass style views live.
- Two draggable vertical cursors (`A` and `B`) are shown for oscilloscope-style measurements of delta X, period, frequency, and per-channel Y values.
- Mouse controls:
  - Wheel: zoom
  - Left drag: box zoom
  - Right drag: pan
  - Middle click: reset full view
  - `R`: reset full view
