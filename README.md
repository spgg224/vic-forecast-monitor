# VIC Forecast Monitor

An interactive historical analysis of when AEMO's public Victorian electricity-market forecasts diverged from actual outcomes.

The project will compare forecast and realised price, demand, renewable output and interconnector conditions across forecast horizons. Its core design preserves both forecast issue time and target time so that every result can be audited for lookahead.

Planned outputs include:

- historical forecast-versus-reality replay;
- forecast-error scorecards and heatmaps;
- an explorer for the largest forecast misses;
- a detailed Victorian price-event case study; and
- an optional calibrated spike-risk model, promoted only if it improves on transparent baselines out of sample.

## Status

The first milestone is complete: a vintage-aware, one-week feasibility prototype using archived AEMO P5MIN forecasts and actual VIC1 prices.

For 1-7 July 2026, the pipeline reconstructed:

- 2,016 realised five-minute VIC1 intervals;
- 24,126 matched P5MIN forecast vintages;
- a median of 12 forecast vintages per target interval;
- zero missing matched actual prices; and
- zero forecast records whose availability timestamp occurred after their target interval.

The sample is a pipeline feasibility test, not yet a representative assessment of forecast performance. In this week, forecast errors ranged from -$214.14/MWh to $314.31/MWh and averaged -$1.60/MWh across all vintages and horizons.

The first scorecard found mean absolute price error increasing from $5.26/MWh at a 0-10 minute horizon to $12.57/MWh at 50-60 minutes. This is a one-week engineering result, not yet a general market conclusion.

![One-hour evolution of P5MIN forecasts for a realised VIC1 interval](output/figures/forecast_vintage_replay.png)

![Mean absolute price error by forecast horizon](output/figures/mae_by_horizon.png)

The pipeline also supports AEMO's compact monthly MMSDM archives. A July 2025 scale test reconstructed 8,928 actual intervals and 107,070 forecast vintages from roughly 55 MB of source downloads, making a year-scale dataset practical.

## Run the prototype

```bash
py -3.12 -m venv .venv
python -m pip install -e ".[dev]"
python -m vic_forecast_monitor.prototype --start 2026-07-01 --end 2026-07-07
python -m vic_forecast_monitor.analysis
python -m vic_forecast_monitor.monthly --month 2025-07
pytest
```

The command downloads and caches original AEMO archives, writes a SHA-256 source manifest, exports parquet datasets and produces a forecast-vintage replay chart. Raw downloads are ignored by Git.

## Principles

- Use only information available at the stated forecast time.
- Preserve forecast vintages and source provenance.
- Prefer simple, defensible analysis over opaque complexity.
- Report negative and inconclusive results honestly.

## Data

The project uses public Australian Energy Market Operator market data. Raw archives will not be committed to Git; reproducible download and transformation scripts will be provided.

## Author

Built by Sparsh Basantani.
