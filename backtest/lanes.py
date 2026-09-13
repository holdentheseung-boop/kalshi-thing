"""
Pluggable entry-condition framework for the NightShark "lanes" strategy.

Each Lane is an independent trade-trigger condition. A trade fires as soon
as ANY lane's check() returns a signal - lanes are OR'd together, never
AND'd:

    "It doesn't have to meet all the triggers, each lane is its own. If it
    doesn't meet one lane, but meets another, it can still get in."
        (source: trading-chat quote, see ASSUMPTIONS.md)

Only ONE lane's internal logic was ever described to us. Everything else
about "the other lanes" (how many, what they check) is unknown, so this
file ships exactly one real lane plus the registry hook to add more later.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Tick:
    ts: float                          # unix seconds
    minutes_left: Optional[float]
    up: Optional[float]                # YES/UP ask price (0-1)
    down: Optional[float]              # NO/DOWN ask price (0-1)
    live_price: Optional[float]        # underlying live price
    open_price: Optional[float]        # "target line" = 15m open/reference price


@dataclass
class LaneSignal:
    lane: str
    side: str                          # "UP" or "DOWN"
    entry_price: float
    reason: str


class Lane:
    name = "base"

    def check(self, history: List[Tick]) -> Optional[LaneSignal]:
        raise NotImplementedError


class TwoCheckDeltaConfirmationLane(Lane):
    """
    Lane #1 - the only lane whose logic is actually known.

    Direct quote: "It's just pulling that data in that case from the
    Kalshi websocket. It means delta has to be moving up/down from the
    target line. It checks it twice to see if the number is
    increasing/decreasing from the target. If it gets two confirmations,
    then it triggers."

    REAL (from the quote):
      - Data source is delta vs. a "target line".
      - Two sequential confirmation checks are required before it fires.
      - The check is about the direction/magnitude of delta movement.

    GUESSED (not in the quote - see ASSUMPTIONS.md):
      - "target line" is interpreted here as the 15-minute open/reference
        price, matching the `Delta := abs(open15m - live)` calculation
        already used in your AHK script.
      - "increasing from the target" is interpreted as |delta| growing
        between consecutive samples (i.e. price accelerating away from
        where the market opened).
      - Delta is measured as a PERCENTAGE of the open price
        ((live - open) / open), not a raw dollar amount. Your AHK script's
        `Delta` config is a raw-dollar threshold, which only makes sense
        for one asset at a time (a $50 move means something very
        different for BTC at ~$65k vs. DOGE at ~$0.08). A percentage
        keeps `step_threshold` comparable across assets in a backtest that
        may span several of them. This is a deliberate deviation from the
        AHK convention, not a confirmed match to the real lanes system.
      - `step_threshold` (how much growth counts as a real confirmation,
        vs. noise) - no value was ever given. This is the tunable
        parameter requested in the task; start conservative and adjust
        once you can compare against real fills.
      - `min_abs_delta` - an optional noise floor, defaults to inactive.
    """

    name = "two_check_delta_confirmation"

    def __init__(self, step_threshold: float, min_abs_delta: float = 0.0):
        self.step_threshold = step_threshold      # GUESS / tunable
        self.min_abs_delta = min_abs_delta         # GUESS / tunable

    def check(self, history: List[Tick]) -> Optional[LaneSignal]:
        if len(history) < 3:
            return None

        window = history[-3:]
        if any(t.live_price is None or t.open_price is None or not t.open_price for t in window):
            return None

        # percentage delta from the open/target line - see class docstring
        d0, d1, d2 = ((t.live_price - t.open_price) / t.open_price for t in window)
        a0, a1, a2 = abs(d0), abs(d1), abs(d2)

        if a2 < self.min_abs_delta:
            return None

        # "checks it twice ... if it gets two confirmations" -> two
        # consecutive increases in |delta|, same direction throughout.
        confirm1 = (a1 - a0) >= self.step_threshold
        confirm2 = (a2 - a1) >= self.step_threshold
        same_direction = (d0 * d1 > 0) and (d1 * d2 > 0)

        if not (confirm1 and confirm2 and same_direction):
            return None

        latest = window[-1]
        side = "UP" if d2 > 0 else "DOWN"
        entry_price = latest.up if side == "UP" else latest.down
        if entry_price is None:
            return None

        return LaneSignal(
            lane=self.name,
            side=side,
            entry_price=entry_price,
            reason=(f"delta confirmed 2x growing away from target "
                    f"({a0:.4f} -> {a1:.4f} -> {a2:.4f}, "
                    f"step_threshold={self.step_threshold})"),
        )


def default_lanes(step_threshold: float, min_abs_delta: float = 0.0) -> List[Lane]:
    """
    Registry of active lanes, checked in order. The engine fires on the
    FIRST lane that returns a signal - since only one lane is implemented,
    that's the only trigger right now.

    To add a guessed/experimental lane #2, #3, etc: subclass Lane in this
    file and append an instance below. Nothing is known about what those
    lanes should check, so none are included by default.
    """
    return [
        TwoCheckDeltaConfirmationLane(step_threshold=step_threshold, min_abs_delta=min_abs_delta),
    ]
