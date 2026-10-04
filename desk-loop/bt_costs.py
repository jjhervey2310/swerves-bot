"""EXPLICIT COST MODEL for backtests. No venue has a built-in default: the caller states the fees it is
testing against and the record travels with the result (research_runs / pa_memory), so a number can
never be quoted without the tier it assumed. Fractions, not percent: 0.0022 == 0.22%."""
import argparse
import dataclasses
import math
import os


@dataclasses.dataclass(frozen=True)
class CostModel:
    maker_fee: float
    taker_fee: float
    venue: str               # required: where these numbers apply
    tier: str                # required: the fee tier / verification they came from
    spread: float = 0.0      # half-spread paid per side on a market fill
    slippage: float = 0.0    # extra per-side impact, size-dependent in reality; a constant here
    note: str = ""

    def __post_init__(self):
        for f in ("maker_fee", "taker_fee", "spread", "slippage"):
            v = getattr(self, f)
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v >= 0.1:
                raise ValueError(f"{f}={v!r}: give a finite fraction in [0, 0.1) (0.0022 == 0.22%)")
        for f in ("venue", "tier"):
            v = getattr(self, f)
            if not isinstance(v, str) or not v.strip() or v.strip().lower() == "unspecified":
                raise ValueError(f"{f} is required — a result without provenance is not evidence")

    def per_side(self, taker: bool = True) -> float:
        """Total one-way cost fraction for a fill."""
        return (self.taker_fee if taker else self.maker_fee) + self.spread + self.slippage

    def round_trip(self, taker: bool = True) -> float:
        return 2 * self.per_side(taker)

    def as_record(self) -> dict:
        return dataclasses.asdict(self)


def scaled(c: CostModel, mult: float) -> CostModel:
    """The same model with EVERY per-side component (fees, half-spread, slippage) multiplied by `mult`: a x1.25 stress on
    0.50%/side is exactly 0.625%/side (round-2 §2 as written). Round-1 code stressed fees only (0.60%) and is left as run."""
    cap = lambda v: min(0.099, v * mult)
    return dataclasses.replace(c, maker_fee=cap(c.maker_fee), taker_fee=cap(c.taker_fee), spread=cap(c.spread), slippage=cap(c.slippage), tier=f"{c.tier} x{mult}")


LEGACY_UNIVERSE = "today's universe.json (survivorship-biased) — DIAGNOSTIC ONLY, not approval evidence"


def stamp(c: CostModel, fill_rule: str, universe: str = LEGACY_UNIVERSE) -> str:
    """One header line for a text result so the assumptions travel with the numbers. Call it BEFORE the
    first print/save so every copy of the output carries it."""
    return (f"ASSUMPTIONS | costs={c.as_record()} | fill={fill_rule} | universe={universe} | "
            f"bars=completed only (market_time.completed_bars), joins by timestamp\n")


def add_cost_args(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Shared CLI flags. Required on purpose: a backtest without stated costs is not a result."""
    p.add_argument("--maker-fee", type=float, required=True, help="fraction, e.g. 0.0022")
    p.add_argument("--taker-fee", type=float, required=True, help="fraction, e.g. 0.0038")
    p.add_argument("--spread", type=float, default=0.0)
    p.add_argument("--slippage", type=float, default=0.0)
    p.add_argument("--venue", required=True)
    p.add_argument("--tier", required=True, help="the fee tier these numbers came from")
    return p


def from_args(a) -> CostModel:
    return CostModel(a.maker_fee, a.taker_fee, a.venue, a.tier, a.spread, a.slippage)


def from_env() -> CostModel:
    """BT_MAKER_FEE, BT_TAKER_FEE, BT_VENUE, BT_TIER (all required); BT_SPREAD, BT_SLIPPAGE optional."""
    try:
        return CostModel(float(os.environ["BT_MAKER_FEE"]), float(os.environ["BT_TAKER_FEE"]),
                         os.environ["BT_VENUE"], os.environ["BT_TIER"],
                         float(os.environ.get("BT_SPREAD", 0)), float(os.environ.get("BT_SLIPPAGE", 0)))
    except (KeyError, ValueError) as e:
        raise SystemExit(f"backtest refused: {e} — costs and provenance must be explicit (BT_MAKER_FEE, BT_TAKER_FEE, BT_VENUE, BT_TIER)")
