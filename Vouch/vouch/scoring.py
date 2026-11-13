"""Vouch Score: a 0 to 100 trust score for one subsidised rooftop solar installation.

The score combines four components, each scored 0 to 100:

    identity     are the panels real, DCR-listed, unique, and scanned on this roof?
    capacity     does the measured kW (from space and from the meter) match the claim?
    persistence  is the array still on the roof and still generating?
    consistency  do the independent measurements agree with each other?

Weights, tolerances and band limits live in default_config.json so they can be
calibrated against field inspection results without touching this code.

This module has no dependencies outside the Python standard library.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).with_name("default_config.json")


def load_config(path: Optional[str] = None) -> dict:
    """Load the calibration file. Pass a path to use your own tuned copy."""
    with open(path or CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@dataclass
class Evidence:
    """Everything the Validate engine knows about one installation.

    Leave a field as None when it has not been measured. A missing measurement
    is scored neutrally and lowers the reported confidence; it is never treated
    as proof of fraud.
    """
    consumer_id: str
    claimed_kw: float
    scheme: str = "PMSGY"                      # "PMSGY" or "ULA"
    # identity
    nameplate_kw: Optional[float] = None       # sum of DCR module ratings, in kW
    serials_scanned_on_roof: Optional[bool] = None
    duplicate_serials: int = 0                 # serials also locked to another consumer
    vendor_inventory_ok: Optional[bool] = None
    # capacity
    footprint_kw: Optional[float] = None       # from satellite / UAV array area
    generation_kw_low: Optional[float] = None  # from meter export and irradiance
    generation_kw_high: Optional[float] = None
    generation_kw_fit: Optional[float] = None  # single figure from the seasonal fit of the same meter data
    telemetry_kw: Optional[float] = None       # from inverter data, when available
    # persistence
    footprint_ratio: Optional[float] = None    # current array area / area at commissioning
    zero_export_days: Optional[int] = None     # consecutive days with no export
    ever_generated: Optional[bool] = None
    fault_logged: bool = False


@dataclass
class VouchResult:
    consumer_id: str
    score: int
    band: str                                   # "GREEN", "AMBER" or "RED"
    components: dict
    confidence: float                           # share of components actually measured
    reasons: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    estimated_kw: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _gap_score(gap: float, tolerance: float, zero_at: float) -> float:
    """100 inside the tolerance, falling in a straight line to 0 at zero_at."""
    gap = abs(gap)
    if gap <= tolerance:
        return 100.0
    if gap >= zero_at:
        return 0.0
    return 100.0 * (zero_at - gap) / (zero_at - tolerance)


def _shortfall(claimed: float, measured: float) -> float:
    """Fraction of the claimed capacity that is missing. Over-delivery is not penalised."""
    if claimed <= 0:
        return 0.0
    return max(0.0, (claimed - measured) / claimed)


def _identity(ev: Evidence, cfg: dict, reasons: list):
    c = cfg["identity"]
    if ev.nameplate_kw is None and ev.serials_scanned_on_roof is None and ev.vendor_inventory_ok is None and ev.duplicate_serials == 0:
        return None
    score = 100.0
    if ev.nameplate_kw is not None:
        short = _shortfall(ev.claimed_kw, ev.nameplate_kw)
        if short > c["nameplate_tolerance"]:
            score = min(score, _gap_score(short, c["nameplate_tolerance"], cfg["capacity"]["zero_score_gap"]))
            reasons.append(f"DCR nameplate sum {ev.nameplate_kw:.2f} kW is {short:.0%} below the {ev.claimed_kw:.2f} kW claimed")
    if ev.serials_scanned_on_roof is False:
        score = min(score, c["not_scanned_score"])
        reasons.append("Module serials were not scanned on the roof")
    if ev.vendor_inventory_ok is False:
        score -= c["inventory_fail_penalty"]
        reasons.append("Vendor's claims exceed its DCR-verified module procurement")
    if ev.duplicate_serials > 0:
        score = 0.0
        reasons.append(f"{ev.duplicate_serials} module serial(s) are also registered to another consumer")
    return max(0.0, score)


def _capacity(ev: Evidence, cfg: dict, reasons: list):
    c = cfg["capacity"]
    scores, estimates = [], []
    if ev.footprint_kw is not None:
        short = _shortfall(ev.claimed_kw, ev.footprint_kw)
        scores.append(_gap_score(short, c["tolerance"], c["zero_score_gap"]))
        estimates.append(ev.footprint_kw)
        if short > c["tolerance"]:
            reasons.append(f"Array seen from above supports {ev.footprint_kw:.2f} kW, {short:.0%} below the claim")
    if ev.generation_kw_low is not None and ev.generation_kw_high is not None:
        # The meter gives a range, because self-consumption is not metered. Use the
        # top of the range: the claim is only doubted if even the most generous
        # reading of the meter cannot explain it.
        short = _shortfall(ev.claimed_kw, ev.generation_kw_high)
        scores.append(_gap_score(short, c["tolerance"], c["zero_score_gap"]))
        estimates.append((ev.generation_kw_low + ev.generation_kw_high) / 2)
        if short > c["tolerance"]:
            reasons.append(f"Meter export supports at most {ev.generation_kw_high:.2f} kW, {short:.0%} below the claim")
    if ev.telemetry_kw is not None:
        short = _shortfall(ev.claimed_kw, ev.telemetry_kw)
        scores.append(_gap_score(short, c["tolerance"], c["zero_score_gap"]))
        estimates.append(ev.telemetry_kw)
        if short > c["tolerance"]:
            reasons.append(f"Inverter data supports {ev.telemetry_kw:.2f} kW, {short:.0%} below the claim")
    if not scores:
        return None, None
    # Two independent methods must both pass, so take the weaker one.
    return min(scores), sum(estimates) / len(estimates)


def _persistence(ev: Evidence, cfg: dict, reasons: list):
    c = cfg["persistence"]
    scores = []
    if ev.footprint_ratio is not None:
        if ev.footprint_ratio >= c["footprint_ok_ratio"]:
            scores.append(100.0)
        elif ev.footprint_ratio <= c["footprint_gone_ratio"]:
            scores.append(0.0)
            reasons.append(f"Only {ev.footprint_ratio:.0%} of the commissioned array is still visible on the roof")
        else:
            span = c["footprint_ok_ratio"] - c["footprint_gone_ratio"]
            scores.append(100.0 * (ev.footprint_ratio - c["footprint_gone_ratio"]) / span)
            reasons.append(f"Array has shrunk to {ev.footprint_ratio:.0%} of its commissioned area")
    if ev.zero_export_days is not None:
        d = ev.zero_export_days
        if d < c["zero_export_amber_days"]:
            s = 100.0
        elif d >= c["zero_export_red_days"]:
            s = 0.0
            reasons.append(f"No export for {d} days")
        else:
            span = c["zero_export_red_days"] - c["zero_export_amber_days"]
            s = 100.0 * (c["zero_export_red_days"] - d) / span
            reasons.append(f"No export for {d} days")
        if s < 100.0 and ev.fault_logged:
            s = min(100.0, s + c["fault_logged_relief"])
            reasons.append("A fault ticket is open, so the outage is treated as a repair in progress")
        scores.append(s)
    if ev.ever_generated is False:
        scores.append(0.0)
        reasons.append("The system has never exported any energy")
    if not scores:
        return None
    return min(scores)


def _consistency(ev: Evidence, cfg: dict, reasons: list):
    c = cfg["consistency"]
    pairs = []
    mid = None
    if ev.generation_kw_low is not None and ev.generation_kw_high is not None:
        mid = (ev.generation_kw_low + ev.generation_kw_high) / 2
    if ev.footprint_kw is not None and mid is not None:
        # Footprint inside (or near) the meter's range means the two agree.
        lo, hi = ev.generation_kw_low, ev.generation_kw_high
        if lo <= ev.footprint_kw <= hi:
            pairs.append(0.0)
        else:
            nearest = lo if ev.footprint_kw < lo else hi
            pairs.append(abs(ev.footprint_kw - nearest) / max(ev.footprint_kw, nearest, 0.1))
    if ev.footprint_kw is not None and ev.nameplate_kw is not None:
        pairs.append(abs(ev.footprint_kw - ev.nameplate_kw) / max(ev.nameplate_kw, 0.1))
    if ev.telemetry_kw is not None and mid is not None:
        pairs.append(abs(ev.telemetry_kw - mid) / max(ev.telemetry_kw, mid, 0.1))
    if not pairs:
        return None
    worst = max(pairs)
    if worst > c["agree_within"]:
        reasons.append(f"Independent measurements disagree with each other by {worst:.0%}")
    return _gap_score(worst, c["agree_within"], c["zero_score_gap"])


def _actions(band: str, ev: Evidence, caps_hit: list) -> list:
    ula = ev.scheme.upper() == "ULA"
    if band == "GREEN":
        acts = ["Digital commissioning certificate stands"]
        acts.append("No payment action (ULA)" if ula else "Release Central subsidy at commissioning; release this year's State instalment")
        return acts
    if band == "AMBER":
        acts = ["Send alert to consumer and vendor", "Vendor to close the ticket within 15 days"]
        if not ula:
            acts.append("Hold this year's State instalment until the score returns to green")
        return acts
    acts = ["Tier-2 remote review", "Order a field check with this finding if unresolved"]
    if ula:
        if "array_missing" in caps_hit or "never_generated" in caps_hit:
            acts.append("Prepare evidence file for recovery and legal action against the beneficiary")
    else:
        acts.append("Hold subsidy; this year's State instalment is forfeited if confirmed")
    if "duplicate_serial" in caps_hit:
        acts.append("Audit the vendor: serial numbers reused across consumers")
    return acts


def score(ev: Evidence, cfg: Optional[dict] = None) -> VouchResult:
    """Compute the Vouch Score for one installation."""
    cfg = cfg or load_config()
    reasons: list = []
    identity = _identity(ev, cfg, reasons)
    capacity, est_kw = _capacity(ev, cfg, reasons)
    persistence = _persistence(ev, cfg, reasons)
    consistency = _consistency(ev, cfg, reasons)

    parts = {"identity": identity, "capacity": capacity, "persistence": persistence, "consistency": consistency}
    measured = [k for k, v in parts.items() if v is not None]
    filled = {k: (v if v is not None else float(cfg["missing_component_score"])) for k, v in parts.items()}
    total = sum(filled[k] * cfg["weights"][k] for k in filled) / sum(cfg["weights"].values())

    caps_hit = []
    view_blocked = False
    caps = cfg["hard_caps"]
    if ev.duplicate_serials > 0:
        caps_hit.append("duplicate_serial")
    if ev.footprint_ratio is not None and ev.footprint_ratio <= cfg["persistence"]["footprint_gone_ratio"]:
        caps_hit.append("array_missing")
    if ev.ever_generated is False:
        caps_hit.append("never_generated")
    # A capacity shortfall is a hard red when the view from above shows it and the
    # meter does not contradict it. The meter contradicts the view from above
    # when its seasonal fit supports the claim (the usual cause is a tree or a
    # water tank hiding part of the array). Without a fit, the meter contradicts
    # only if even its lowest reading supports the claim.
    tol = cfg["capacity"]["tolerance"]
    fp_short = _shortfall(ev.claimed_kw, ev.footprint_kw) if ev.footprint_kw is not None else None
    gen_short_hi = _shortfall(ev.claimed_kw, ev.generation_kw_high) if ev.generation_kw_high is not None else None
    gen_short_lo = _shortfall(ev.claimed_kw, ev.generation_kw_low) if ev.generation_kw_low is not None else None
    fit_short = _shortfall(ev.claimed_kw, ev.generation_kw_fit) if ev.generation_kw_fit is not None else None
    if fp_short is not None and fp_short > cfg["red_capacity_gap"]:
        if fit_short is not None:
            meter_supports_claim = fit_short <= cfg["meter_supports_claim_within"]
        else:
            meter_supports_claim = gen_short_lo is not None and gen_short_lo <= tol
        if meter_supports_claim:
            view_blocked = True
        else:
            caps_hit.append("capacity_gap_over_red")
    elif fp_short is None:
        if fit_short is not None and fit_short > cfg["red_capacity_gap"]:
            caps_hit.append("capacity_gap_over_red")
        elif fit_short is None and gen_short_hi is not None and gen_short_hi > cfg["red_capacity_gap"]:
            caps_hit.append("capacity_gap_over_red")
    for name in caps_hit:
        total = min(total, caps[name])

    final = int(round(max(0.0, min(100.0, total))))
    band = "GREEN" if final >= cfg["bands"]["green_min"] else "AMBER" if final >= cfg["bands"]["amber_min"] else "RED"
    if view_blocked and not caps_hit:
        # Not fraud on this evidence, but not clean either: keep it out of red,
        # hold it at amber at best, and ask for a clearer picture.
        total = min(max(total, float(cfg["bands"]["amber_min"])), float(cfg["bands"]["green_min"]) - 1)
        reasons.append("The meter supports the claimed size, so the array is probably partly hidden from above; a clearer image or drone pass is needed")
        final = int(round(max(0.0, min(100.0, total))))
        band = "AMBER"
    if not measured:
        reasons.append("No measurements available yet; score is provisional")
    return VouchResult(
        consumer_id=ev.consumer_id,
        score=final,
        band=band,
        components={k: (None if v is None else round(v, 1)) for k, v in parts.items()},
        confidence=round(len(measured) / len(parts), 2),
        reasons=reasons,
        actions=_actions(band, ev, caps_hit),
        estimated_kw=None if est_kw is None else round(est_kw, 2),
    )
