#!/usr/bin/env python3
"""
CLI entry point for the lanes-strategy backtest.

Usage:
    python3 run_backtest.py path/to/logs.jsonl
    python3 run_backtest.py path/to/logs.jsonl --step-threshold 0.02
    python3 run_backtest.py path/to/logs.jsonl --sweep

Every default below is labeled REAL (taken directly from your existing AHK
config or the source quotes) or GUESS (no information exists, tune freely).
"""
import argparse
from statistics import mean

from engine import run_backtest, log_span_hours


def summarize(results, span_hours):
    n = len(results)
    entered = [r for r in results if r.entered]
    resolved = [r for r in entered if r.pnl is not None]
    unresolved = [r for r in entered if r.pnl is None]
    wins = [r for r in resolved if r.pnl > 0]
    losses = [r for r in resolved if r.pnl <= 0]

    print(f"Sessions in log:        {n}")
    if n == 0:
        print("  (no sessions parsed - check ALIASES in engine.py against your real jsonl field names)")
        return
    print(f"Entries:                {len(entered)}  ({100*len(entered)/n:.1f}% of sessions)")
    print(f"  target ballpark:      20-30% of markets (from source quote)")
    if unresolved:
        print(f"  unresolved/unknown settlement: {len(unresolved)}  "
              f"(no 'settlement' field and price never converged near 0/1 - see engine.py)")
    if span_hours and entered:
        cadence = span_hours / len(entered)
        print(f"Entry cadence:          1 every {cadence:.2f}h  (log spans ~{span_hours:.1f}h)")
        print(f"  target ballpark:      1 every 1.5-2h (from source quote)")
    if resolved:
        win_rate = 100 * len(wins) / len(resolved)
        net_pnl = sum(r.pnl for r in resolved)
        print(f"Win rate:               {win_rate:.1f}%  ({len(wins)}W / {len(losses)}L)")
        print(f"Net PnL:                {net_pnl:+.2f}")
        if wins:
            print(f"Avg win:                {mean(r.pnl for r in wins):+.2f}")
        if losses:
            print(f"Avg loss:               {mean(r.pnl for r in losses):+.2f}")
    else:
        print("No resolved trades - nothing to report win rate / PnL on.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jsonl_path")
    ap.add_argument("--entry-window-min", type=float, default=8.0,
                     help="REAL (from your AHK 'timeDelay'): minutes-remaining window entries are allowed in. Default 8.")
    ap.add_argument("--step-threshold", type=float, default=0.0005,
                     help="GUESS/tunable: min growth in |delta| (as a fraction of open price, e.g. 0.0005 = 5 bps) required at each of the 2 confirmation steps. Default is a placeholder.")
    ap.add_argument("--min-abs-delta", type=float, default=0.0,
                     help="GUESS/tunable: noise floor below which delta moves are ignored. Default 0 (inactive).")
    ap.add_argument("--order-size", type=float, default=30,
                     help="REAL (from your AHK 'orderSize'): contracts per entry. Default 30.")
    ap.add_argument("--stoploss", type=float, default=None,
                     help="Optional stoploss price. Omit for hold-to-resolution, which is the REAL default per source quotes.")
    ap.add_argument("--sweep", action="store_true",
                     help="Sweep --step-threshold over a range and report entry frequency for each, to help calibrate against the 20-30%%/1.5-2h anecdote.")
    args = ap.parse_args()

    span_hours = log_span_hours(args.jsonl_path)

    if args.sweep:
        print("Calibration sweep (GUESS parameter step-threshold vs. resulting entry frequency)")
        print("=" * 78)
        for st in [0.0, 0.000005, 0.00001, 0.000015, 0.00002, 0.00003, 0.00005, 0.00008, 0.00012, 0.0002]:
            results = run_backtest(args.jsonl_path, args.entry_window_min, st,
                                    args.order_size, args.stoploss, args.min_abs_delta)
            n = len(results)
            entered = sum(1 for r in results if r.entered)
            pct = (100 * entered / n) if n else 0.0
            cadence = f"{span_hours/entered:.2f}h" if (span_hours and entered) else "n/a"
            print(f"step_threshold={st:<6}  entries={entered:>4}/{n:<4} ({pct:5.1f}%)  cadence=1/{cadence}")
        print()
        print("Pick the step_threshold whose entries%/cadence lands closest to 20-30% / 1.5-2h,")
        print("then re-run without --sweep using that value.")
        return

    results = run_backtest(args.jsonl_path, args.entry_window_min, args.step_threshold,
                            args.order_size, args.stoploss, args.min_abs_delta)
    print(f"Lane: two_check_delta_confirmation | step_threshold={args.step_threshold} "
          f"(GUESS) | entry_window={args.entry_window_min}min (REAL) | "
          f"stoploss={'none/hold-to-resolution (REAL default)' if args.stoploss is None else args.stoploss}")
    print("=" * 78)
    summarize(results, span_hours)


if __name__ == "__main__":
    main()
