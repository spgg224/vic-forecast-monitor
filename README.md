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

Early development. The first milestone is a one-week feasibility prototype using archived AEMO P5MIN forecasts and actual VIC1 prices.

## Principles

- Use only information available at the stated forecast time.
- Preserve forecast vintages and source provenance.
- Prefer simple, defensible analysis over opaque complexity.
- Report negative and inconclusive results honestly.

## Data

The project uses public Australian Energy Market Operator market data. Raw archives will not be committed to Git; reproducible download and transformation scripts will be provided.

## Author

Built by Sparsh Basantani.

