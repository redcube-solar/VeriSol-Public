"""Build the evidence file for a red installation.

The file gathers, in one JSON document, what an officer needs to start a field
visit, a recovery notice or (for ULA roofs) legal action: the claim, what each
independent source measured, the locked serial list and the dated history.

It is a record of measurements. Whether and how it is used in proceedings is
for the Department and the DISCOM legal cells to decide.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .scoring import Evidence, VouchResult


def build_evidence_file(
    ev: Evidence,
    result: VouchResult,
    serials: Optional[list] = None,
    export_history: Optional[list] = None,
    footprint_history: Optional[list] = None,
    commissioning_record: Optional[dict] = None,
) -> dict:
    return {
        "document": "VeriSol evidence file",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "consumer_id": ev.consumer_id,
        "scheme": ev.scheme,
        "claim": {"claimed_kw": ev.claimed_kw, "dcr_nameplate_kw": ev.nameplate_kw},
        "vouch": {
            "score": result.score,
            "band": result.band,
            "components": result.components,
            "confidence": result.confidence,
            "findings": result.reasons,
            "recommended_actions": result.actions,
        },
        "measurements": {
            "footprint_kw": ev.footprint_kw,
            "generation_kw_range": [ev.generation_kw_low, ev.generation_kw_high],
            "telemetry_kw": ev.telemetry_kw,
            "array_area_now_vs_commissioning": ev.footprint_ratio,
            "consecutive_zero_export_days": ev.zero_export_days,
        },
        "locked_module_serials": serials or [],
        "meter_export_history": export_history or [],
        "array_footprint_history": footprint_history or [],
        "commissioning_record": commissioning_record or {},
    }


def write_evidence_file(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
