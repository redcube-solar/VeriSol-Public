"""One-command demo on invented data.

    python run_demo.py

Reads the measurements of 2,000 invented roofs (Validate/sample_data/measurements.csv,
produced by the proprietary VeriSol Validate engine from the invented raw data
beside it), scores each roof with the open Vouch scoring in this repository, and
compares the verdicts with the truth that was planted.
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "Vouch"))
sys.path.insert(0, str(ROOT / "Validate"))

from validate import measurements  # noqa: E402
from vouch import score            # noqa: E402

FRAUD = {"undersized", "never_installed", "removed", "duplicate_serial"}
LABELS = ("honest", "shaded_honest", "occluded_honest", "undersized", "never_installed", "removed", "duplicate_serial")


def main() -> dict:
    data = ROOT / "Validate" / "sample_data"
    with open(data / "truth_labels.csv", newline="", encoding="utf-8") as fh:
        truth = {r["consumer_id"]: r["truth"] for r in csv.DictReader(fh)}
    scored = [(vendor, ev, score(ev)) for vendor, ev in measurements.read(str(data / "measurements.csv"))]

    table = defaultdict(Counter)
    for _vendor, ev, res in scored:
        table[truth[ev.consumer_id]][res.band] += 1
    print(f"\nVeriSol demo on {len(scored)} invented roofs (no real data)\n")
    print(f"{'planted truth':<20}{'GREEN':>7}{'AMBER':>7}{'RED':>7}")
    for label in LABELS:
        c = table[label]
        print(f"{label:<20}{c['GREEN']:>7}{c['AMBER']:>7}{c['RED']:>7}")

    fraud_total = sum(sum(table[k].values()) for k in FRAUD)
    fraud_red = sum(table[k]["RED"] for k in FRAUD)
    honest_total = len(scored) - fraud_total
    honest_red = sum(table[k]["RED"] for k in table if k not in FRAUD)
    summary = {
        "roofs": len(scored), "fraud_planted": fraud_total, "fraud_flagged_red": fraud_red,
        "honest": honest_total, "honest_flagged_red": honest_red,
        "accuracy_pct": round(100 * (fraud_red + honest_total - honest_red) / len(scored), 2),
    }
    print(f"\nPlanted fraud flagged red: {fraud_red} of {fraud_total}")
    print(f"Honest roofs wrongly flagged red: {honest_red} of {honest_total}")
    print(f"Red / not-red verdict correct on {summary['accuracy_pct']} per cent of roofs")
    print("This is on invented data. Accuracy on real roofs is not known until field checks are done.")
    print("\nVendor scorecard (lowest average first):")
    for row in sorted(measurements.vendor_scorecard([(v, r) for v, _e, r in scored]), key=lambda r: r["average_score"])[:5]:
        print(f"  {row['vendor_id']}: average {row['average_score']}, {row['red']} red of {row['roofs']} roofs")
    return summary


if __name__ == "__main__":
    main()
