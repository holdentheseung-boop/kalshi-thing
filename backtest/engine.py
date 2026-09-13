"""
Backtest engine for the NightShark "lanes" entry strategy.

Reads logged Kalshi 15-minute market ticks from one or more .jsonl files
(one JSON object per line, each line a poll snapshot across all tracked
assets), groups them into per-market sessions by ticker (marketName),
restricts entries to a "last N minutes" window (matches the `timeDelay`
window your AHK script already uses), runs the lane framework (lanes.py)
tick-by-tick, and by default holds every position to resolution - no
stoploss - per:

    "Not often [use a stoploss]. From all the tests I have run, it seems
    like holding to resolution is more profitable even if you have a few
    more losses... holding to resolution saves a ton on fees."

Real log schema (confirmed from your uploaded price-data files):

    {"timestamp": "...", "timestampUtc": "2026-09-12T15:00:00Z",
     "assets": [
        {"assetName": "BTC", "marketName": "KXBTC15M-26SEP121115-15",
         "marketCloseUtc": "2026-09-12T15:15:00Z",
         "upPrice": 0.55, "downPrice": 0.46,
         "underlyingOpen": 77444.20, "underlyingCurrent": 77445.51},
        ... one object per tracked asset ...
     ]}

There is no explicit settlement/result field. Kalshi's 15-minute
up/down-vs-open markets settle based on whether the underlying price at
close is above or below the price at open, so settlement is DERIVED here
as: underlyingCurrent at the session's last observed tick vs.
underlyingOpen at the session's first observed tick. See
`_resolve_settlement` and ASSUMPTIONS.md for the caveats (mainly: sessions
truncated at the very start/end of your log window don't have a full
lifecycle and are excluded from stats rather than guessed at).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from lanes import Tick, default_lanes


def _parse_iso(s: str) -> Optional[float]:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


@dataclass
class SessionResult:
    ticker: str
    asset: str
    complete: bool = False              # full lifecycle observed (see _resolve_settlement)
    entered: bool = False
    lane: Optional[str] = None
    side: Optional[str] = None
    entry_price: Optional[float] = None
    entry_ts: Optional[float] = None
    settlement: Optional[int] = None    # 1 = UP/YES won, 0 = DOWN/NO won
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None


@dataclass
class _RawSession:
    asset: str
    ticks: List[Tuple[float, dict]] = field(default_factory=list)   # (ts_epoch, fields)


def iter_asset_records(paths: List[str]):
    """Yields (ticker, asset, ts_epoch, fields) for every asset entry in
    every line of every file, in the file order given (pass files in
    chronological order for multi-file logs)."""
    for path in paths:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = rec.get("timestampUtc") or rec.get("timestamp")
                if not ts_raw:
                    continue
                ts = _parse_iso(ts_raw)
                if ts is None:
                    continue
                for a in rec.get("assets", []):
                    ticker = a.get("marketName")
                    if not ticker:
                        continue
                    close_raw = a.get("marketCloseUtc")
                    close_ts = _parse_iso(close_raw) if close_raw else None
                    minutes_left = (close_ts - ts) / 60.0 if close_ts is not None else None
                    yield ticker, (a.get("assetName") or "?"), ts, {
                        "up": a.get("upPrice"),
                        "down": a.get("downPrice"),
                        "open": a.get("underlyingOpen"),
                        "current": a.get("underlyingCurrent"),
                        "minutes_left": minutes_left,
                    }


def load_sessions(paths: List[str]) -> Dict[str, _RawSession]:
    sessions: Dict[str, _RawSession] = {}
    for ticker, asset, ts, fields in iter_asset_records(paths):
        sess = sessions.setdefault(ticker, _RawSession(asset=asset))
        sess.ticks.append((ts, fields))
    for sess in sessions.values():
        sess.ticks.sort(key=lambda x: x[0])
    return sessions


def _to_ticks(raw: _RawSession) -> List[Tick]:
    return [
        Tick(
            ts=ts,
            minutes_left=fields["minutes_left"],
            up=fields["up"],
            down=fields["down"],
            live_price=fields["current"],
            open_price=fields["open"],
        )
        for ts, fields in raw.ticks
    ]


# A session is "complete" if the log actually captured its full lifecycle:
# starts near a fresh 15-minute window and ends near expiry. Sessions
# truncated at the very start/end of the supplied log files don't have a
# real open or a real close in the data, so they're excluded from
# win-rate/PnL stats rather than guessed at.
COMPLETE_START_MIN_LEFT = 13.5   # first tick must show close to the full 15m left
COMPLETE_END_MAX_LEFT = 0.5      # last tick must show close to 0m left


def _resolve_settlement(ticks: List[Tick]) -> Tuple[bool, Optional[int]]:
    minutes = [t.minutes_left for t in ticks if t.minutes_left is not None]
    if not minutes:
        return False, None
    complete = (max(minutes) >= COMPLETE_START_MIN_LEFT) and (min(minutes) <= COMPLETE_END_MAX_LEFT)
    if not complete:
        return False, None

    open_price = next((t.open_price for t in ticks if t.open_price is not None), None)
    close_price = next((t.live_price for t in reversed(ticks) if t.live_price is not None), None)
    if open_price is None or close_price is None or close_price == open_price:
        return complete, None
    return complete, 1 if close_price > open_price else 0


def run_backtest(
    paths: List[str],
    entry_window_minutes: float,
    step_threshold: float,
    order_size: float,
    stoploss: Optional[float] = None,   # None = hold-to-resolution (the default per source quotes)
    min_abs_delta: float = 0.0,
    max_entry_price: float = 1.0,       # NOT from source / opt-in cap, see lanes.py
) -> List[SessionResult]:
    raw_sessions = load_sessions(paths)
    results: List[SessionResult] = []

    for ticker, raw in raw_sessions.items():
        ticks = _to_ticks(raw)
        if not ticks:
            continue

        complete, settlement = _resolve_settlement(ticks)
        result = SessionResult(ticker=ticker, asset=raw.asset, complete=complete, settlement=settlement)
        lanes = default_lanes(step_threshold, min_abs_delta, max_entry_price)
        history: List[Tick] = []
        entered_side: Optional[str] = None

        for t in ticks:
            if t.minutes_left is None or t.minutes_left > entry_window_minutes or t.minutes_left <= 0:
                continue
            history.append(t)

            if entered_side is None:
                for lane in lanes:
                    sig = lane.check(history)
                    if sig:
                        entered_side = sig.side
                        result.entered = True
                        result.lane = sig.lane
                        result.side = sig.side
                        result.entry_price = sig.entry_price
                        result.entry_ts = t.ts
                        break
            elif stoploss is not None:
                current = t.up if entered_side == "UP" else t.down
                if current is not None and current < stoploss:
                    result.exit_price = current
                    result.pnl = (current - result.entry_price) * order_size
                    result.exit_reason = f"stoploss<{stoploss}"
                    entered_side = "closed"
                    break

        if result.entered and result.exit_price is None and complete and settlement is not None:
            exit_price = 1.0 if (
                (result.side == "UP" and settlement == 1) or
                (result.side == "DOWN" and settlement == 0)
            ) else 0.0
            result.exit_price = exit_price
            result.pnl = (exit_price - result.entry_price) * order_size
            result.exit_reason = "held_to_resolution"

        results.append(result)

    return results


def log_span_hours(paths: List[str]) -> Optional[float]:
    min_ts, max_ts = None, None
    for _, _, ts, _ in iter_asset_records(paths):
        min_ts = ts if min_ts is None else min(min_ts, ts)
        max_ts = ts if max_ts is None else max(max_ts, ts)
    if min_ts is None or max_ts is None or max_ts <= min_ts:
        return None
    return (max_ts - min_ts) / 3600.0
