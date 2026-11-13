# Vouch: the scoring algorithm

Turns what is known about one rooftop into a Vouch Score from 0 to 100.

- `vouch/scoring.py`: the score, the band, the reasons and the actions
- `vouch/default_config.json`: every weight and threshold. Tune these against field inspection results
- `vouch/evidence_file.py`: the evidence file written for a red roof

```python
from vouch import Evidence, score
r = score(Evidence(consumer_id="OD000001", claimed_kw=3.24, nameplate_kw=3.24,
                   footprint_kw=2.1, generation_kw_low=1.7, generation_kw_high=2.2))
print(r.score, r.band, r.reasons)
```

Rules worth knowing: a measurement that is missing is scored neutrally and lowers the confidence, never the verdict; delivering more than claimed is not penalised; a capacity shortfall becomes a hard red only when the view from above shows it and the meter does not contradict it. If the meter's seasonal fit (`generation_kw_fit`) supports the claimed size, the array is treated as partly hidden from above: the roof is held at amber and a clearer image is requested.
