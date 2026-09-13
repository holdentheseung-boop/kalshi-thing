#!/usr/bin/env python3
"""
Generates a SYNTHETIC jsonl file that mimics the guessed log schema, purely
so the lanes framework/engine can be exercised end-to-end before real logs
exist. This is NOT real market data and any backtest numbers produced from
it are demo output only - they say nothing about real performance.

Once you point run_backtest.py at your actual logged jsonl (and confirm/
correct the field names in engine.py's ALIASES), discard this file's output.
"""
import json
import random
import sys

random.seed(7)

OUT = sys.argv[1] if len(sys.argv) > 1 else "sample_data.jsonl"
NUM_SESSIONS = 400          # ~ a few days of 15-min BTC markets
TICK_SECONDS = 1.0
SESSION_SECONDS = 15 * 60

def gen_session(session_idx, t0):
    open_price = 65000 + random.uniform(-2000, 2000)
    live = open_price
    trend = random.choice([-1, 0, 0, 1]) * random.uniform(0, 3.0)  # most sessions chop
    ticker = f"KXBTC15M-{session_idx:05d}"
    recs = []
    n_ticks = int(SESSION_SECONDS / TICK_SECONDS)
    for i in range(n_ticks):
        t = t0 + i * TICK_SECONDS
        live += trend * 0.02 + random.uniform(-1.5, 1.5)
        minutes_left = round((SESSION_SECONDS - i * TICK_SECONDS) / 60.0, 3)
        delta_frac = max(-0.5, min(0.5, (live - open_price) / 400.0))
        up = max(0.01, min(0.99, 0.5 + delta_frac))
        down = round(1 - up, 4)
        up = round(up, 4)
        recs.append({
            "ts": t,
            "asset": "BTC",
            "ticker": ticker,
            "up": up,
            "down": down,
            "live_price": round(live, 2),
            "open_price": round(open_price, 2),
            "minutes_left": minutes_left,
        })
    settlement = "yes" if live > open_price else "no"
    recs.append({
        "ts": t0 + SESSION_SECONDS,
        "asset": "BTC",
        "ticker": ticker,
        "settlement": settlement,
    })
    return recs, t0 + SESSION_SECONDS + 15  # small gap to next session

def main():
    t = 1_700_000_000.0
    with open(OUT, "w") as f:
        for i in range(NUM_SESSIONS):
            recs, t = gen_session(i, t)
            for r in recs:
                f.write(json.dumps(r) + "\n")
    print(f"Wrote {NUM_SESSIONS} synthetic sessions to {OUT}")

if __name__ == "__main__":
    main()
