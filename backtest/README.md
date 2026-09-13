# Lanes strategy backtest

Prototype "lanes" entry framework for NightSharkV2, per the task in this
branch. **Read `ASSUMPTIONS.md` first** — it draws the line between what
came directly from the trading-chat quotes and what had to be guessed.

## Files

- `lanes.py` — the pluggable lane framework. A trade fires if ANY lane's
  `check()` returns a signal. Currently ships one real lane
  (`TwoCheckDeltaConfirmationLane`); everything else about "the other
  lanes" is unknown, so none are stubbed in.
- `engine.py` — jsonl loader, session grouping, entry-window filter,
  simulation loop, hold-to-resolution settlement.
- `run_backtest.py` — CLI. Reports entry frequency, win rate, net PnL; has
  a `--sweep` mode to calibrate the delta-confirmation threshold.
- `generate_sample_data.py` — generates a **synthetic** jsonl file so the
  pipeline can be exercised before real logs are available. Not real data.

## Quickstart (with your real logs)

```bash
# 1. Point the engine at your real jsonl and fix field names if needed —
#    see ALIASES in engine.py and the "jsonl schema" row in ASSUMPTIONS.md
python3 run_backtest.py /path/to/your/logs.jsonl --sweep

# 2. Pick the step-threshold whose entry%/cadence lands near the
#    20-30% / 1.5-2h ballpark from the quotes, then:
python3 run_backtest.py /path/to/your/logs.jsonl --step-threshold <value>

# Optional: turn on a stoploss (off by default = hold to resolution)
python3 run_backtest.py /path/to/your/logs.jsonl --step-threshold <value> --stoploss 0.40
```

## Demo run (synthetic data only — not real numbers)

```bash
python3 generate_sample_data.py sample_data.jsonl
python3 run_backtest.py sample_data.jsonl --sweep
python3 run_backtest.py sample_data.jsonl --step-threshold 0.000022
```

This exists only to prove the mechanics work (any-lane-fires, two-check
confirmation, hold-to-resolution PnL). The win rate/PnL it prints say
nothing about real performance — see the "Bottom line" section of
`ASSUMPTIONS.md`.
