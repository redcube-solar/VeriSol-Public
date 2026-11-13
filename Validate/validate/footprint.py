"""Array footprint from imagery.

The production design runs a segmentation model over ORSAC satellite or UAV
imagery to find the solar array on each registered roof and measure its area.
That model needs labelled Odisha rooftop imagery to train, which this
repository does not yet have.

What is here is the interface the engine uses, so the model can be dropped in
later without changing anything else:

    FootprintSource.area_m2(consumer_id, on_date) -> projected area or None

Two implementations are provided: one reading a CSV of areas (which is how
manually measured or model-produced areas arrive today), and a placeholder for
the model itself.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from typing import Optional


class FootprintSource:
    def area_m2(self, consumer_id: str, on_date: Optional[str] = None) -> Optional[float]:
        raise NotImplementedError

    def history(self, consumer_id: str) -> list:
        return []


class CsvFootprintSource(FootprintSource):
    """Areas from a CSV with columns: consumer_id, date (YYYY-MM-DD), area_m2."""

    def __init__(self, path: str):
        self._rows = defaultdict(list)
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                self._rows[row["consumer_id"]].append((row["date"], float(row["area_m2"])))
        for rows in self._rows.values():
            rows.sort()

    def history(self, consumer_id: str) -> list:
        return [{"date": d, "area_m2": a} for d, a in self._rows.get(consumer_id, [])]

    def area_m2(self, consumer_id: str, on_date: Optional[str] = None) -> Optional[float]:
        rows = self._rows.get(consumer_id)
        if not rows:
            return None
        if on_date is None:
            return rows[-1][1]
        earlier = [a for d, a in rows if d <= on_date]
        return earlier[-1] if earlier else None

    def first_area_m2(self, consumer_id: str) -> Optional[float]:
        rows = self._rows.get(consumer_id)
        return rows[0][1] if rows else None


class SegmentationFootprintSource(FootprintSource):
    """Placeholder for the imagery model (PyTorch segmentation over ORSAC tiles).

    To implement: fetch the image tile for the roof polygon, run the model,
    count array pixels, multiply by the ground area of one pixel.
    """

    def area_m2(self, consumer_id: str, on_date: Optional[str] = None) -> Optional[float]:
        raise NotImplementedError("Imagery model not trained yet. Use CsvFootprintSource meanwhile.")
