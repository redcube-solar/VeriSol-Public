import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vouch import Evidence, score, build_evidence_file


def honest(**kw):
    base = dict(consumer_id="C1", claimed_kw=3.0, nameplate_kw=3.24, serials_scanned_on_roof=True,
                footprint_kw=3.1, generation_kw_low=2.6, generation_kw_high=3.3,
                footprint_ratio=1.0, zero_export_days=0, ever_generated=True)
    base.update(kw)
    return Evidence(**base)


def test_honest_roof_is_green():
    r = score(honest())
    assert r.band == "GREEN" and r.score >= 90 and r.confidence == 1.0


def test_undersized_roof_is_red_when_both_methods_agree():
    r = score(honest(nameplate_kw=2.16, footprint_kw=2.1, generation_kw_low=1.7, generation_kw_high=2.2))
    assert r.band == "RED"
    assert any("below the claim" in x for x in r.reasons)


def test_one_weak_method_alone_is_not_red():
    # Shaded but honest roof: footprint is right, generation is low.
    r = score(honest(generation_kw_low=1.9, generation_kw_high=2.4))
    assert r.band in ("AMBER", "GREEN")


def test_duplicate_serial_is_red_and_triggers_vendor_audit():
    r = score(honest(duplicate_serials=2))
    assert r.band == "RED" and r.score <= 30
    assert any("Audit the vendor" in a for a in r.actions)


def test_removed_ula_array_asks_for_evidence_file():
    r = score(honest(scheme="ULA", footprint_ratio=0.0, zero_export_days=120,
                     footprint_kw=0.0, generation_kw_low=0.0, generation_kw_high=0.0))
    assert r.band == "RED"
    assert any("evidence file" in a for a in r.actions)


def test_outage_with_fault_ticket_is_treated_gently():
    no_ticket = score(honest(zero_export_days=70))
    ticket = score(honest(zero_export_days=70, fault_logged=True))
    assert ticket.score > no_ticket.score


def test_missing_data_is_neutral_and_lowers_confidence():
    r = score(Evidence(consumer_id="C2", claimed_kw=3.0))
    assert r.confidence == 0.0 and r.band == "AMBER"


def test_over_delivery_is_not_penalised():
    r = score(honest(footprint_kw=3.6, generation_kw_low=3.0, generation_kw_high=3.8, nameplate_kw=3.78))
    assert r.band == "GREEN"


def test_evidence_file_has_the_findings():
    ev = honest(scheme="ULA", footprint_ratio=0.0, footprint_kw=0.0)
    doc = build_evidence_file(ev, score(ev), serials=["S1", "S2"])
    assert doc["locked_module_serials"] == ["S1", "S2"] and doc["vouch"]["band"] == "RED"


def test_hidden_array_is_amber_not_red_when_the_meter_supports_the_claim():
    r = score(Evidence(consumer_id="X", claimed_kw=3.24, nameplate_kw=3.24, footprint_kw=2.27, footprint_ratio=1.0,
                       generation_kw_low=2.4, generation_kw_high=3.6, generation_kw_fit=3.2))
    assert r.band == "AMBER" and any("hidden from above" in x for x in r.reasons)


def test_short_array_is_red_when_the_meter_fit_agrees_with_the_view_from_above():
    r = score(Evidence(consumer_id="X", claimed_kw=3.24, nameplate_kw=3.24, footprint_kw=2.2, footprint_ratio=1.0,
                       generation_kw_low=1.6, generation_kw_high=3.0, generation_kw_fit=2.25))
    assert r.band == "RED"
