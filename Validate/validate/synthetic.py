"""Make a realistic but entirely invented data set for demos and tests.

No real consumer, vendor or module appears here. Each roof is given a hidden
"truth" label (honest, undersized, never_installed, removed, duplicate_serial,
shaded_honest, occluded_honest) so the engine's flags can be checked against what was planted.

    python -m validate.synthetic --out sample_data --roofs 2000   (from inside the Validate folder)
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import random

from . import irradiance

MODULE = {"wp": 540, "length_m": 2.278, "width_m": 1.134}
MONTHS = [f"2026-{m:02d}" for m in range(1, 11)]  # Jan to Oct 2026

# (label, share of roofs)
MIX = [("honest", 0.75), ("shaded_honest", 0.06), ("occluded_honest", 0.05), ("undersized", 0.05), ("never_installed", 0.02),
       ("removed", 0.04), ("duplicate_serial", 0.03)]


def _pick(rng: random.Random) -> str:
    x, acc = rng.random(), 0.0
    for label, share in MIX:
        acc += share
        if x <= acc:
            return label
    return "honest"


def generate(out_dir: str, roofs: int = 2000, seed: int = 7) -> dict:
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)
    installs, modules, exports, footprints, truth = [], [], [], [], {}
    area_one = MODULE["length_m"] * MODULE["width_m"]
    vendors = [f"V{n:02d}" for n in range(1, 13)]
    bad_vendor = "V07"  # most planted fraud is concentrated here, as in real life
    spare_serials = []

    for n in range(1, roofs + 1):
        cid = f"OD{n:06d}"
        label = _pick(rng)
        scheme = "ULA" if rng.random() < 0.35 else "PMSGY"
        claimed_modules = 2 if scheme == "ULA" else rng.choice([4, 6, 6, 6, 8, 10])
        if label == "undersized" and claimed_modules < 4:
            label = "honest"
        vendor = bad_vendor if (label not in ("honest", "shaded_honest", "occluded_honest") and rng.random() < 0.6) else rng.choice(vendors)
        claimed_kw = round(claimed_modules * MODULE["wp"] / 1000, 2)
        tilt = rng.choice([10, 12, 15, 18])
        pre_solar = rng.randint(90, 160) if scheme == "ULA" else rng.randint(150, 320)

        # What is really on the roof, month by month
        real_modules = claimed_modules
        if label == "undersized":
            real_modules = claimed_modules - max(2, claimed_modules // 3)
        if label == "never_installed":
            real_modules = 0
        removed_from = rng.randint(4, 7) if label == "removed" else None
        pr = rng.uniform(0.70, 0.80)
        home_share = rng.uniform(0.25, 0.55)  # each home uses a different share of its old consumption in daylight
        if label == "shaded_honest":
            pr = rng.uniform(0.60, 0.66)

        # DCR records always show the full claim: the paperwork is what fraud fakes
        serials = [f"RC{n:06d}{k:02d}" for k in range(claimed_modules)]
        if label == "duplicate_serial" and spare_serials:
            take = min(2, len(spare_serials))
            serials[:take] = [spare_serials.pop() for _ in range(take)]
        elif label == "honest" and len(spare_serials) < 40:
            spare_serials.extend(serials[:1])
        for s in serials:
            modules.append({"serial": s, "consumer_id": cid, "vendor_id": vendor, **MODULE})

        for i, month in enumerate(MONTHS):
            on_roof = real_modules if (removed_from is None or i < removed_from) else 0
            kw = on_roof * MODULE["wp"] / 1000
            sun = irradiance.climatology_monthly(int(month[:4]), int(month[5:7])) * rng.uniform(0.93, 1.07)
            generation = kw * sun * pr
            self_use = min(generation, home_share * rng.uniform(0.85, 1.15) * pre_solar)
            exports.append({"consumer_id": cid, "month": month, "export_kwh": round(max(0.0, generation - self_use), 1)})

        for date, idx in (("2026-02-15", 1), ("2026-10-15", 9)):
            on_roof = real_modules if (removed_from is None or idx < removed_from) else 0
            area = on_roof * area_one * math.cos(math.radians(tilt)) * rng.uniform(0.96, 1.04)
            if label == "occluded_honest":
                area *= 0.70  # a tree or water tank hides part of the array from above
            footprints.append({"consumer_id": cid, "date": date, "area_m2": round(area, 2)})

        installs.append({
            "consumer_id": cid, "scheme": scheme, "vendor_id": vendor, "claimed_kw": claimed_kw,
            "lat": round(20.27 + rng.uniform(-0.15, 0.15), 5), "lon": round(85.84 + rng.uniform(-0.15, 0.15), 5),
            "tilt_deg": tilt, "pre_solar_kwh": pre_solar,
            "commissioned_on": "2026-01-20" if label == "duplicate_serial" else f"2026-01-{rng.randint(2, 12):02d}",
            "scanned_on_roof": "", "fault_logged": "",
        })
        truth[cid] = label

    def dump(name, rows):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    dump("installations.csv", installs)
    dump("dcr_modules.csv", modules)
    dump("meter_export.csv", exports)
    dump("footprint.csv", footprints)
    dump("truth_labels.csv", [{"consumer_id": c, "truth": t} for c, t in truth.items()])
    return truth


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate an invented VeriSol data set")
    ap.add_argument("--out", required=True)
    ap.add_argument("--roofs", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    truth = generate(args.out, args.roofs, args.seed)
    print(f"Wrote {len(truth)} invented roofs to {args.out}")


if __name__ == "__main__":
    main()
