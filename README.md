<p align="center"><img src="assets/verisol-logo.png" alt="VeriSol: Verify. Validate. Vouch." width="520"></p>

# VeriSol

**Verify. Validate. Vouch.** A platform to check that subsidised rooftop solar systems are real, correctly sized and still in use. This repository is its open part: the installer app, the Vouch scoring, the data formats and a demo on invented data. The measurement and data-fusion engine is proprietary to RedCube Solar.

Built by RedCube Solar for OSFIC 2026 (Odisha Seva First Innovation Challenge), Renewable Energy theme, registration OSFIC-KH-2026-378.

## Status

This is a working prototype at design stage. Everything runs and is tested, but only on invented data. Nothing here has yet been run on real installations.

| Part | Folder | What works today | What is not built yet |
| --- | --- | --- | --- |
| **Verify** (on the roof) | `Verify/` | Server and phone web page: geo-fenced module scanning, DCR check against a sample registry, one-serial-one-roof lock, array measurement, ULA custody undertaking, public serial look-up | Vendor login, real NISE DCR API, AR measurement, the telemetry Node |
| **Validate** (in the cloud) | `Validate/` | Open here: registry checks, the measurements format, measurements of 2,000 invented roofs, the invented raw data. Proprietary, not in this repository: capacity measurement from imagery and meter data, and the fusion of the five sources | The imagery model that measures arrays from ORSAC tiles |
| **Vouch** (for the asset) | `Vouch/` | The 0 to 100 score, bands, reasons, recommended actions, evidence file | Calibration against real inspection results |

## Try it

You need Python 3.10 or newer.

```
python run_demo.py
```

This reads the measurements of 2,000 invented roofs (about 12 per cent with planted fraud), scores each with the Vouch code in this repository, and prints what was caught. It needs nothing installed beyond Python itself.

Result (invented data):

| Planted truth | Green | Amber | Red |
| --- | --- | --- | --- |
| Honest | 1,530 | 0 | 0 |
| Honest but shaded | 124 | 0 | 0 |
| Honest, array partly hidden from above | 0 | 90 | 11 |
| Undersized | 0 | 0 | 74 |
| Never installed | 0 | 0 | 33 |
| Removed after commissioning | 0 | 0 | 77 |
| Duplicate serial | 0 | 0 | 61 |

All 245 planted frauds were flagged red, and 11 of 1,755 honest roofs were wrongly flagged red, so the red or not-red verdict was right on 99.45 per cent of roofs.

Read these numbers as a check that the logic works, not as accuracy on real roofs. The data is invented, and the noise in it (sunlight, household use, performance) follows assumptions we chose. Real accuracy can only come from real data and field checks.

To run the installer app:

```
cd Verify
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Open http://127.0.0.1:8000. Sample serials to scan are `DEMO5400001` to `DEMO5402000` (2,000 invented modules). Camera scanning and location need HTTPS on a phone; on the same computer `localhost` is enough.

To run the tests:

```
pip install pytest httpx
python -m pytest Vouch Validate Verify
```

## How the parts connect

1. **Verify** locks module serials to a consumer at commissioning and exports them (`GET /api/export`).
2. **Validate** (proprietary engine) reads those records with DISCOM meter export and array areas, measures each roof's capacity in independent ways, and writes one row of measurements per roof (`Validate/validate/measurements.py` describes the format).
3. **Vouch** turns the measurements into a score, a band (green, amber, red), the reasons, and the action to take.

The Vouch calibration lives in `Vouch/vouch/default_config.json`. Change the weights and thresholds there, not in the code.

## Data and privacy

The repository contains no real consumer, vendor or module data. `Validate/sample_data` and `Verify/backend/sample_dcr_registry.json` are invented. Do not commit real data to a public repository.

## Licence

The code in this repository is under the MIT licence. See `LICENSE`. The licence covers this repository only; the VeriSol Validate engine and the calibrated Vouch model are separate and proprietary.
