"""Checks on DCR module records.

Input is a list of module rows as they come from the DCR Verification Portal
or the Verify app: {"serial", "consumer_id", "vendor_id", "wp"}.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def nameplate_kw_by_consumer(modules: Iterable[dict]) -> dict:
    """Sum of rated module power per consumer, in kW."""
    out = defaultdict(float)
    for m in modules:
        out[m["consumer_id"]] += float(m["wp"]) / 1000.0
    return dict(out)


def duplicate_serials(modules: Iterable[dict], registered_on: dict = None) -> dict:
    """Serials registered to more than one consumer.

    registered_on maps consumer_id to the date (YYYY-MM-DD) its modules were
    registered. When dates are known, the earliest holder of a serial is taken
    as the rightful one and only the later claimants are flagged. Without
    dates, every holder is flagged, because nothing says who came first.

    Returns {consumer_id: [serials it shares with an earlier holder]}.
    """
    registered_on = registered_on or {}
    owners = defaultdict(set)
    for m in modules:
        owners[m["serial"]].add(m["consumer_id"])
    out = defaultdict(list)
    for serial, consumers in owners.items():
        if len(consumers) < 2:
            continue
        dated = sorted((registered_on[c], c) for c in consumers if registered_on.get(c))
        first = dated[0][1] if len(dated) == len(consumers) and dated[0][0] != dated[1][0] else None
        for c in consumers:
            if c != first:
                out[c].append(serial)
    return dict(out)


def vendor_inventory_check(modules: Iterable[dict], procured_modules_by_vendor: dict) -> dict:
    """Has each vendor claimed more modules than the DCR portal says it bought?

    Returns {vendor_id: True if within inventory, False if over}. Vendors with
    no procurement record are left out (unknown, not failed).
    """
    used = defaultdict(set)
    for m in modules:
        used[m["vendor_id"]].add(m["serial"])
    return {v: len(s) <= procured_modules_by_vendor[v] for v, s in used.items() if v in procured_modules_by_vendor}
