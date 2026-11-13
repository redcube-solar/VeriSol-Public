import csv
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Vouch"))
sys.path.insert(0, str(ROOT / "Validate"))

from validate import dcr, irradiance, synthetic, measurements
from vouch import score


def test_duplicate_serial_flags_only_the_later_claimant_when_dates_known():
    mods = [{"serial": "S1", "consumer_id": "A", "vendor_id": "V", "wp": 540},
            {"serial": "S1", "consumer_id": "B", "vendor_id": "V", "wp": 540}]
    assert set(dcr.duplicate_serials(mods)) == {"A", "B"}
    assert set(dcr.duplicate_serials(mods, {"A": "2026-01-05", "B": "2026-02-01"})) == {"B"}


def test_vendor_inventory():
    mods = [{"serial": f"S{i}", "consumer_id": "A", "vendor_id": "V1", "wp": 540} for i in range(10)]
    assert dcr.vendor_inventory_check(mods, {"V1": 8}) == {"V1": False}
    assert dcr.vendor_inventory_check(mods, {"V1": 12}) == {"V1": True}


def test_irradiance_fallback_covers_every_month():
    sun = irradiance.monthly_series([f"2026-{m:02d}" for m in range(1, 13)])
    assert len(sun) == 12 and all(80 < h < 220 for h in sun)


def test_synthetic_data_has_every_file_and_a_truth_label_per_roof(tmp_path):
    truth = synthetic.generate(str(tmp_path), roofs=50, seed=1)
    assert len(truth) == 50
    for name in ("installations.csv", "dcr_modules.csv", "meter_export.csv", "footprint.csv", "truth_labels.csv"):
        assert (tmp_path / name).exists()


def test_measurements_of_two_thousand_roofs_score_at_least_99_per_cent():
    """The shipped measurements file, scored by the open Vouch code, against the planted truth."""
    data = ROOT / "Validate" / "sample_data"
    truth = {r["consumer_id"]: r["truth"] for r in csv.DictReader(open(data / "truth_labels.csv", newline="", encoding="utf-8"))}
    fraud = {"undersized", "never_installed", "removed", "duplicate_serial"}
    rows = measurements.read(str(data / "measurements.csv"))
    right = sum((score(ev).band == "RED") == (truth[ev.consumer_id] in fraud) for _v, ev in rows)
    assert len(rows) == 2000 and right / 2000 >= 0.99
    card = measurements.vendor_scorecard([(v, score(ev)) for v, ev in rows])
    assert sum(r["roofs"] for r in card) == 2000
