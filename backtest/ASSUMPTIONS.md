# Lanes strategy — what's real vs. guessed

This backtest was built with **no jsonl logs, AHK scripts, `server.ps1`, or
`dashboard.html` present anywhere in the repo or container** — the repo had
zero commits. The AHK script pasted into the task request was used as the
source of truth for "real" config values (it's your actual working bot);
everything about the "lanes" strategy itself comes from three secondhand
quotes with no code, thresholds, or counts attached. This file draws the
line between the two so you know exactly what to trust.

## Directly from the quotes (real, not guessed)

- **Two-check delta confirmation**: entries require delta to be moving
  away from a reference line, confirmed on *two* consecutive checks before
  firing. ("It checks it twice ... If it gets two confirmations, then it
  triggers.")
- **Lanes are OR'd, not AND'd**: any one lane firing is sufficient; a
  market that fails lane A can still be entered via lane B. ("It doesn't
  have to meet all the triggers, each lane is its own.")
- **Selectivity**: normally enters ~20-30% of markets, roughly once every
  1.5-2 hours; a choppy day with tight deltas can push that much lower
  (only twice in a day, per the quote).
- **No stoploss by default; hold to resolution.** Explicitly stated as
  more profitable in their own testing and cited as a fee-savings
  mechanism.

## Guessed / placeholder (flagged in code, tune freely)

| Item | What was guessed | Where |
|---|---|---|
| `step_threshold` | The magnitude of delta growth needed per confirmation step. **No value was ever given.** Currently a placeholder tuned only to land the *synthetic demo data* in the 20-30%/1.5-2h ballpark — it has no bearing on your real markets. | `lanes.py`, CLI `--step-threshold` |
| "Target line" definition | Interpreted as the 15-minute open/reference price, matching the `Delta := abs(open15m - live)` calc already in your AHK script. Could instead mean a strike price, a moving average, or something else entirely. | `lanes.py` docstring |
| Delta units | Measured as **percentage of open price** ((live − open) / open) rather than a raw dollar amount, so one threshold works across assets of very different price scales (BTC ≈ $65k vs. DOGE ≈ $0.08). Your AHK `Delta` setting is raw-dollar and per-asset; this is a deliberate deviation, not a confirmed match. | `lanes.py` |
| `min_abs_delta` noise floor | Defaults to 0 (inactive) — nothing in the quotes implies a floor exists. | `lanes.py`, CLI `--min-abs-delta` |
| Entry window | Reused your AHK `timeDelay` (last 8 minutes of the 15m market) since the quotes never mention a window at all. | `run_backtest.py` `--entry-window-min` |
| Position size | Reused your AHK `orderSize` (30 contracts) — this is your real config value, just not confirmed to apply to the lanes system. | `run_backtest.py` `--order-size` |
| Other lanes (#2, #3, ...) | **Completely unknown.** No count, no logic. Only lane #1 (delta confirmation) is implemented. The framework in `lanes.py` is built so you can add more `Lane` subclasses later without touching the engine. | `lanes.py` `default_lanes()` |
| jsonl schema | No log file existed to inspect. `engine.py`'s `ALIASES` dict is a best-effort guess based on field names already used in your AHK script (`up`, `down`, `open15m`, live price, `minutesLeft`, ticker). **This almost certainly needs correcting once you supply real logs.** | `engine.py` |
| Settlement source | No settlement field was known to exist, so the engine first looks for one (`settlement`/`result`/`outcome`), and falls back to inferring from ask prices converging to ~0 or ~1 near market close. | `engine.py` `_resolve_settlement()` |

## Bottom line

Every number this backtest currently reports comes from a **400-session
synthetic random-walk dataset** (`generate_sample_data.py`) generated only
to prove the pipeline runs end-to-end — entry-fires-on-any-lane, two-check
confirmation, hold-to-resolution settlement, PnL accounting. It is not
your market, not your data, and the ~92% win rate it shows is an artifact
of how the synthetic trend/settlement was constructed, not a real result.

**To get real numbers**: send/push your actual jsonl logs, tell Claude the
real field names if they differ from `engine.py`'s `ALIASES`, and re-run
`run_backtest.py --sweep` against them to calibrate `step_threshold` for
real.
