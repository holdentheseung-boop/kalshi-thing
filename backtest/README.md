# Lanes strategy backtest

Prototype "lanes" entry framework for NightSharkV2. **Read
`ASSUMPTIONS.md` first** — it draws the line between what came directly
from the trading-chat quotes, what's confirmed from your real jsonl logs,
and what's still a guess.

## Files

- `lanes.py` — the pluggable lane framework. A trade fires if ANY lane's
  `check()` returns a signal. Currently ships one real lane
  (`TwoCheckDeltaConfirmationLane`); everything else about "the other
  lanes" is unknown, so none are stubbed in.
- `engine.py` — jsonl loader (matches your real log schema: per-line poll
  snapshots with a nested `assets` array), session grouping, entry-window
  filter, simulation loop, hold-to-resolution settlement derived from
  underlying price at open vs. close.
- `run_backtest.py` — CLI. Reports entry frequency, win rate, net PnL,
  per-asset breakdown; has a `--sweep` mode to calibrate the
  delta-confirmation threshold per asset.
- `generate_sample_data.py` — generates a synthetic jsonl file for smoke
  testing only. Not real data; not used once real logs exist.
- `data/` — your real price logs go here (gitignored — not committed).

## Quickstart

```bash
# 1. Calibrate per-asset (volatility differs a lot between assets - a
#    threshold tuned for BTC will fire way too often on ETH, and may
#    barely fire at all on SOL - see ASSUMPTIONS.md)
python3 run_backtest.py data/*.jsonl --sweep --asset BTC

# 2. Run with the calibrated threshold
python3 run_backtest.py data/*.jsonl --step-threshold 0.00002 --asset BTC

# Optional: cap entry price so the lane can't fire on an already-decided
# market seconds before close (seen in real data at 0.99+ prices) - not
# in the source quotes, purely opt-in:
python3 run_backtest.py data/*.jsonl --step-threshold 0.00002 --asset BTC --max-entry-price 0.85

# Optional: turn on a stoploss (off by default = hold to resolution)
python3 run_backtest.py data/*.jsonl --step-threshold 0.00002 --stoploss 0.40
```

Pass multiple jsonl files in chronological order as positional args;
they're concatenated in the order given.

## Demo run (synthetic data only — not real numbers)

```bash
python3 generate_sample_data.py /tmp/sample_data.jsonl
python3 run_backtest.py /tmp/sample_data.jsonl --sweep
```

Only useful for confirming the pipeline runs end-to-end; says nothing
about real performance.
