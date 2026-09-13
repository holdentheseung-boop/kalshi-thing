"""
Backtest engine for the NightShark "lanes" entry strategy.

Reads logged Kalshi 15-minute market ticks from a .jsonl file (one JSON
object per line), groups them into per-market sessions by ticker, restricts
entries to a "last N minutes" window (matches the `timeDelay` window your
AHK script already uses), runs the lane framework (lanes.py) tick-by-tick,
and by default holds every position to resolution - no stoploss - per:

    "Not often [use a stoploss]. From all the tests I have run, it seems
    like holding to resolution is more profitable even if you have a few
    more losses... holding to resolution saves a ton on fees."

IMPORTANT: no server.ps1, dashboard.html, or *.jsonl logs existed anywhere
in this repo/container when this was built (the repo had zero commits).
ALIASES below is a best-effort GUESS at your real field names, based only
on the variable names already used in your AHK script (up, down, open15m,
live price, minutesLeft, ticker). If your actual jsonl uses different keys,
either tell Claude the real schema or add the key names to ALIASES.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from lanes import Tick, default_lanes

# --- GUESSED field-name aliases: edit to match your real jsonl -------------
ALIASES = {
    "ts":           ["ts", "timestamp", "time", "t"],
    "asset":        ["asset", "symbol"],
    "ticker":       ["ticker", "market_ticker", "marketTicker"],
    "up":           ["up", "yes_ask", "yes_price", "up_price"],
    "down":         ["down", "no_ask", "no_price", "down_price"],
    "live_price":   ["live_price", "livePrice", "price", "underlying_price"],
    "open_price":   ["open_price", "open15m", "open", "openPrice"],
    "minutes_left": ["minutes_left", "minutesLeft", "mins_left"],
    "settlement":   ["settlement", "result", "outcome"],
}


def _get(rec: dict, key: str):
    for alias in ALIASES[key]:
        if alias in rec and rec[alias] not in (None, ""):
            return rec[alias]
    return None


def _num(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_epoch(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


@dataclass
class SessionResult:
    ticker: str
    asset: str
    entered: bool = False
    lane: Optional[str] = None
    side: Optional[str] = None
    entry_price: Optional[float] = None
    entry_ts: Optional[float] = None
    settlement: Optional[int] = None            # 1 = UP/YES won, 0 = DOWN/NO won
    settlement_source: Optional[str] = None     # "explicit" or "inferred_converged_price"
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None


def load_sessions(path: str) -> Dict[str, List[dict]]:
    sessions: Dict[str, List[dict]] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ticker = _get(rec, "ticker") or "unknown"
            sessions.setdefault(ticker, []).append(rec)
    return sessions


def _build_ticks(records: List[dict]) -> Tuple[List[Tick], str]:
    ticks = []
    for rec in records:
        ts = _to_epoch(_get(rec, "ts")) or 0.0
        ticks.append(Tick(
            ts=ts,
            minutes_left=_num(_get(rec, "minutes_left")),
            up=_num(_get(rec, "up")),
            down=_num(_get(rec, "down")),
            live_price=_num(_get(rec, "live_price")),
            open_price=_num(_get(rec, "open_price")),
        ))
    ticks.sort(key=lambda t: t.ts)
    asset = _get(records[0], "asset") or "?"
    return ticks, asset


def _resolve_settlement(records: List[dict], ticks: List[Tick]) -> Tuple[Optional[int], Optional[str]]:
    """Prefer an explicit settlement field; otherwise infer from ask
    prices converging to 0/1 near resolution (how binary markets behave
    as they close). Returns (1=UP/YES won, 0=DOWN/NO won) or (None, None)
    if it can't be determined either way."""
    for rec in records:
        raw = _get(rec, "settlement")
        if raw is not None:
            s = str(raw).strip().lower()
            if s in ("yes", "up", "1", "true"):
                return 1, "explicit"
            if s in ("no", "down", "0", "false"):
                return 0, "explicit"

    for t in reversed(ticks):
        if t.up is not None and t.up >= 0.99:
            return 1, "inferred_converged_price"
        if t.down is not None and t.down >= 0.99:
            return 0, "inferred_converged_price"
    return None, None


def run_backtest(
    path: str,
    entry_window_minutes: float,
    step_threshold: float,
    order_size: float,
    stoploss: Optional[float] = None,   # None = hold-to-resolution (the default per source quotes)
    min_abs_delta: float = 0.0,
) -> List[SessionResult]:
    sessions = load_sessions(path)
    results: List[SessionResult] = []

    for ticker, records in sessions.items():
        ticks, asset = _build_ticks(records)
        if not ticks:
            continue

        result = SessionResult(ticker=ticker, asset=asset)
        lanes = default_lanes(step_threshold, min_abs_delta)
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

        if result.entered and result.exit_price is None:
            settlement, source = _resolve_settlement(records, ticks)
            result.settlement = settlement
            result.settlement_source = source
            if settlement is not None:
                exit_price = 1.0 if (
                    (result.side == "UP" and settlement == 1) or
                    (result.side == "DOWN" and settlement == 0)
                ) else 0.0
                result.exit_price = exit_price
                result.pnl = (exit_price - result.entry_price) * order_size
                result.exit_reason = "held_to_resolution"

        results.append(result)

    return results


def log_span_hours(path: str) -> Optional[float]:
    """Wall-clock span covered by the whole log file, for entry-cadence stats."""
    min_ts, max_ts = None, None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _to_epoch(_get(rec, "ts"))
            if ts is None:
                continue
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)
    if min_ts is None or max_ts is None or max_ts <= min_ts:
        return None
    return (max_ts - min_ts) / 3600.0
