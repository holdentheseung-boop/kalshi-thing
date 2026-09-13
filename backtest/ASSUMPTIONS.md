# Lanes strategy — what's real vs. guessed

This backtest was originally built with zero jsonl logs available (empty
repo). It has since been run against your 5 real log files covering
2026-09-12 15:00 UTC → 2026-09-13 01:00 UTC (10 hours, BTC/ETH/SOL, ~40
fifteen-minute sessions per asset). This file draws the line between what
came directly from the trading-chat quotes, what's now confirmed from your
real data, and what's still a guess.

## Directly from the quotes (real, not guessed)

- **Two-check delta confirmation**: entries require delta to be moving
  away from a reference line, confirmed on *two* consecutive checks before
  firing.
- **Lanes are OR'd, not AND'd**: any one lane firing is sufficient.
- **Selectivity**: normally enters ~20-30% of markets, roughly once every
  1.5-2 hours; choppy days can push that much lower.
- **No stoploss by default; hold to resolution.**

## Confirmed from your real jsonl logs (no longer guesses)

- **Schema**: each line is a poll snapshot — `timestampUtc` plus an
  `assets` array of `{assetName, marketName, marketCloseUtc, upPrice,
  downPrice, underlyingOpen, underlyingCurrent}`. `engine.py` parses this
  directly now (the old alias-guessing loader was replaced).
- **"Target line" = `underlyingOpen`**: confirmed to exist exactly as
  guessed, and it updates tick-to-tick rather than being frozen at session
  start (it visibly moved ~$1.50 within the first 2 seconds of a session
  in your data) — so the lane compares against whatever open value was
  reported at that instant, matching how the live bot would see it.
- **No settlement field exists in the logs.** Kalshi's 15-minute up/down
  markets settle by comparing the underlying price at close to the price
  at open, so `engine.py` derives settlement as: `underlyingCurrent` at
  the session's last observed tick vs. `underlyingOpen` at its first
  observed tick. Sessions truncated at the very start/end of your log
  window (no full lifecycle captured) are excluded from stats rather than
  guessed at — 3 of 123 sessions in your 5 files.

## Guessed / placeholder — now backed by real calibration data

| Item | What was guessed | Real-data finding |
|---|---|---|
| `step_threshold` (delta % growth per confirmation step) | No value was ever given. | **Asset-dependent — a single threshold does not transfer.** At `2e-5` (0.002%): BTC → 15% entries, 1 every 1.67h (closest match to the 20-30%/1.5-2h target). ETH is far more volatile — the same threshold gives 37.5% at nearly 3x the frequency; matching ETH to the same target needs ~4-5e-5. SOL barely moved enough to trigger at any threshold tested (1 entry all day at nearly every setting) — either SOL chopped much less that day, or its price granularity doesn't suit this delta measure. **Calibrate per-asset with `--sweep --asset <NAME>`.** |
| Delta units | Guessed as % of open price rather than raw dollars, for cross-asset comparability. | Confirmed necessary — BTC (~$77k) and SOL (~$102) real prices in this data differ by ~750x; a raw-dollar threshold could never work for both. |
| Entry price / lateness bound | Not mentioned in the quotes at all. | **This matters.** With no cap, 2 of 6 BTC entries fired with ~12 seconds left in the market at prices of 0.996/0.999 — the outcome was already essentially decided, so the "win" was a few cents on a near-zero-edge bet, not a real predictive entry. This inflates win rate. Added `--max-entry-price` as an opt-in cap (inactive by default = 1.0, matching "nothing said about this in the quotes"). At `--max-entry-price 0.85` (borrowing your own AHK EntryRange upper bound as a reference point, not a confirmed match) BTC drops to 2 entries/5.0%/1-per-5h — too strict to hit the target on this single day, but removes the degenerate late entries. There's a real tradeoff here between hitting the quoted frequency and avoiding degenerate entries that your one day of data doesn't fully resolve either way. |
| Other lanes (#2, #3, ...) | Completely unknown. | Still completely unknown — only lane #1 is implemented. |
| Position size / entry window | Reused your AHK `orderSize`=30 and `timeDelay`=8min. | Unchanged — still your real config values, not confirmed to apply to lanes specifically. |

## Bottom line / how to read the numbers below

- The "20-30% of markets / once per 1.5-2h" target is hard to hit exactly
  on a *single day* of data for a *single asset* — with only 40 sessions
  for BTC, each percentage point is 0.4 sessions, so precision is limited.
  The source's own quote acknowledges today-style chop can suppress hits
  well below normal ("today ... it has only jumped in twice").
- Treat the reported win rate/PnL as **directional, not final** — one
  session's PnL swings a lot on a 6-trade sample, and the late-entry issue
  above means some of that win rate is close-to-certain outcomes rather
  than genuine edge.
- More days of logs (especially calmer, more "normal" days per the
  source's own framing) would materially tighten the threshold
  calibration and make the win rate/PnL numbers trustworthy.
