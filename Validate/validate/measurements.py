"""Read the measurements file that the VeriSol Validate engine produces.

The engine that turns raw data (DCR records, meter export, satellite imagery,
Verify app records) into per-roof measurements is proprietary to RedCube Solar
and is not part of this repository. What is open is its output format, so that
anyone can check how a measurement becomes a Vouch Score.

measurements.csv, one row per installation (blank = not measured):

    consumer_id, scheme, vendor_id, claimed_kw
    nameplate_kw             sum of DCR module ratings
    duplicate_serials        serials also registered to another consumer
    vendor_inventory_ok      1/0: vendor's claims within its DCR-verified procurement
    serials_scanned_on_roof  1/0: from the Verify app
    footprint_kw             capacity supported by the array seen from above
    footprint_ratio          array area now / array area at commissioning
    generation_kw_low/high   capacity range supported by net-meter export
    generation_kw_fit        single capacity figure from net-meter export
    telemetry_kw             from inverter data, where available
    zero_export_days         consecutive days with no export
    ever_generated           1/0
    fault_logged             1/0
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Vouch"))

from vouch import Evidence  # noqa: E402

_FLOATS = ("nameplate_kw", "footprint_kw", "footprint_ratio", "generation_kw_low", "generation_kw_high",
           "generation_kw_fit", "telemetry_kw")
_FLAGS = ("vendor_inventory_ok", "serials_scanned_on_roof", "ever_generated")


def read(path: str) -> list:
    """Return a list of (vendor_id, Evidence), one per row."""
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ev = Evidence(consumer_id=row["consumer_id"], claimed_kw=float(row["claimed_kw"]), scheme=row.get("scheme") or "PMSGY")
            for k in _FLOATS:
                if row.get(k, "") != "":
                    setattr(ev, k, float(row[k]))
            for k in _FLAGS:
                if row.get(k, "") != "":
                    setattr(ev, k, row[k] == "1")
            if row.get("zero_export_days", "") != "":
                ev.zero_export_days = int(row["zero_export_days"])
            ev.duplicate_serials = int(row.get("duplicate_serials") or 0)
            ev.fault_logged = row.get("fault_logged") == "1"
            out.append((row.get("vendor_id", ""), ev))
    return out


def vendor_scorecard(scored: list) -> list:
    """Roll roof scores up to the vendor. `scored` is a list of (vendor_id, VouchResult)."""
    by_vendor = defaultdict(list)
    for vendor, res in scored:
        by_vendor[vendor].append(res)
    return [{
        "vendor_id": v, "roofs": len(rs), "average_score": round(sum(r.score for r in rs) / len(rs), 1),
        "red": sum(r.band == "RED" for r in rs), "amber": sum(r.band == "AMBER" for r in rs),
        "green": sum(r.band == "GREEN" for r in rs),
    } for v, rs in sorted(by_vendor.items())]
