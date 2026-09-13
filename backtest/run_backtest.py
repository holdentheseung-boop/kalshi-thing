#!/usr/bin/env python3
"""
CLI entry point for the lanes-strategy backtest.

Usage:
    python3 run_backtest.py logs1.jsonl logs2.jsonl ...   # pass in chronological order
    python3 run_backtest.py logs.jsonl --step-threshold 0.00003
    python3 run_backtest.py logs.jsonl --sweep

Every default below is labeled REAL (taken directly from your existing AHK
config or the source quotes) or GUESS (no information exists, tune freely).
"""
import argparse
from collections import Counter
from statistics import mean

from engine import run_backtest, log_span_hours


def summarize(results, span_hours, asset_filter=None):
    if asset_filter:
        results = [r for r in results if r.asset == asset_filter]
    complete = [r for r in results if r.complete]
    incomplete = [r for r in results if not r.complete]
    n = len(complete)
    entered = [r for r in complete if r.entered]
    resolved = [r for r in entered if r.pnl is not None]
    unresolved = [r for r in entered if r.pnl is None]
    wins = [r for r in resolved if r.pnl > 0]
    losses = [r for r in resolved if r.pnl <= 0]

    print(f"Sessions in log:        {len(results)}  ({len(complete)} complete, {len(incomplete)} truncated at log edges - excluded)")
    if n == 0:
        print("  (no complete sessions parsed - check the jsonl schema against engine.py)")
        return
    print(f"Entries:                {len(entered)}  ({100*len(entered)/n:.1f}% of complete sessions)")
    print(f"  target ballpark:      20-30% of markets (from source quote)")
    if unresolved:
        print(f"  unresolved: {len(unresolved)} (entered but settlement direction was a push/unknown)")
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
        by_asset = Counter(r.asset for r in resolved)
        by_asset_wins = Counter(r.asset for r in wins)
        print("By asset:")
        for asset, cnt in by_asset.most_common():
            w = by_asset_wins.get(asset, 0)
            pnl = sum(r.pnl for r in resolved if r.asset == asset)
            print(f"  {asset:<5} entries={cnt:<4} win_rate={100*w/cnt:5.1f}%  pnl={pnl:+.2f}")
    else:
        print("No resolved trades - nothing to report win rate / PnL on.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jsonl_paths", nargs="+", help="one or more jsonl log files, in chronological order")
    ap.add_argument("--entry-window-min", type=float, default=8.0,
                     help="REAL (from your AHK 'timeDelay'): minutes-remaining window entries are allowed in. Default 8.")
    ap.add_argument("--step-threshold", type=float, default=0.00002,
                     help="GUESS/tunable: min growth in |delta| (as a fraction of open price) required at each of the 2 confirmation steps.")
    ap.add_argument("--min-abs-delta", type=float, default=0.0,
                     help="GUESS/tunable: noise floor below which delta moves are ignored. Default 0 (inactive).")
    ap.add_argument("--max-entry-price", type=float, default=1.0,
                     help="NOT from source quotes: cap entry price so the lane can't fire on an already-decided market (seen at 0.99+ with seconds left in real data). Default 1.0 (inactive).")
    ap.add_argument("--order-size", type=float, default=30,
                     help="REAL (from your AHK 'orderSize'): contracts per entry. Default 30.")
    ap.add_argument("--stoploss", type=float, default=None,
                     help="Optional stoploss price. Omit for hold-to-resolution, which is the REAL default per source quotes.")
    ap.add_argument("--sweep", action="store_true",
                     help="Sweep --step-threshold over a range and report entry frequency for each, to help calibrate against the 20-30%%/1.5-2h anecdote.")
    ap.add_argument("--asset", default=None,
                     help="Filter to a single asset (e.g. BTC). Volatility differs a lot per asset, so a threshold calibrated on one won't transfer to another - see ASSUMPTIONS.md.")
    args = ap.parse_args()

    span_hours = log_span_hours(args.jsonl_paths)

    if args.sweep:
        print("Calibration sweep (GUESS parameter step-threshold vs. resulting entry frequency)")
        if args.asset:
            print(f"Asset filter: {args.asset}")
        print("=" * 78)
        for st in [0.0, 0.000005, 0.00001, 0.000015, 0.00002, 0.000025, 0.00003, 0.00004, 0.00005, 0.00008, 0.00012, 0.0002, 0.0003, 0.0005]:
            results = run_backtest(args.jsonl_paths, args.entry_window_min, st,
                                    args.order_size, args.stoploss, args.min_abs_delta, args.max_entry_price)
            if args.asset:
                results = [r for r in results if r.asset == args.asset]
            complete = [r for r in results if r.complete]
            n = len(complete)
            entered = sum(1 for r in complete if r.entered)
            pct = (100 * entered / n) if n else 0.0
            cadence = f"{span_hours/entered:.2f}h" if (span_hours and entered) else "n/a"
            print(f"step_threshold={st:<9}  entries={entered:>4}/{n:<4} ({pct:5.1f}%)  cadence=1/{cadence}")
        print()
        print("Pick the step_threshold whose entries%/cadence lands closest to 20-30% / 1.5-2h,")
        print("then re-run without --sweep using that value.")
        return

    results = run_backtest(args.jsonl_paths, args.entry_window_min, args.step_threshold,
                            args.order_size, args.stoploss, args.min_abs_delta, args.max_entry_price)
    print(f"Lane: two_check_delta_confirmation | step_threshold={args.step_threshold} "
          f"(GUESS) | entry_window={args.entry_window_min}min (REAL) | "
          f"stoploss={'none/hold-to-resolution (REAL default)' if args.stoploss is None else args.stoploss}"
          + (f" | asset={args.asset}" if args.asset else ""))
    print("=" * 78)
    summarize(results, span_hours, args.asset)


if __name__ == "__main__":
    main()
