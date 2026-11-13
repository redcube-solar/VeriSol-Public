# Validate: the central engine

The Validate engine measures every roof from the DCR registry, the National Portal, the DISCOM net meter, satellite imagery and the Verify app, and hands the measurements to Vouch.

**The measurement and data-fusion engine is proprietary to RedCube Solar and is not in this repository.** What is open here is everything needed to check its output:

- `validate/measurements.py`: the format of the measurements file the engine produces, and a reader for it
- `sample_data/measurements.csv`: the engine's measurements of 2,000 invented roofs
- `sample_data/*.csv`: the invented raw data those measurements were made from, with the planted truth in `truth_labels.csv`
- `validate/dcr.py`: registry checks (nameplate sums, duplicate serials, vendor inventory)
- `validate/irradiance.py`: sunlight from NASA POWER, with built-in typical values for coastal Odisha as fallback
- `validate/footprint.py`: the array-area input format
- `validate/synthetic.py`: the generator of the invented data

Run `python run_demo.py` from the repository root to score the measurements with Vouch and compare the verdicts with the planted truth.

Regenerating the invented raw data with `synthetic.py` does not regenerate `measurements.csv`; that needs the engine.

The NASA POWER call has not been tested from the build environment, which had no internet access to that site. Test it once before relying on it.
