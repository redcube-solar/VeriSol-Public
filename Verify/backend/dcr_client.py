"""Look up a module serial on the DCR Verification Portal.

The real portal (NISE / MNRE) does not publish an open API, so access has to be
requested. Until then the app uses MockDcrClient, which reads a local JSON file
shaped like the data the portal holds. NiseDcrClient is the place to put the
real calls once access is granted; nothing else in the app needs to change.
"""
from __future__ import annotations

import json
from typing import Optional


class DcrClient:
    def lookup(self, serial: str) -> Optional[dict]:
        """Return the module record, or None if the serial is unknown.

        Record keys: serial, manufacturer, model, wp, length_m, width_m,
        dcr_compliant (bool), allotted_vendor (vendor id or None).
        """
        raise NotImplementedError


class MockDcrClient(DcrClient):
    def __init__(self, path: str):
        with open(path, encoding="utf-8") as fh:
            self._by_serial = {m["serial"]: m for m in json.load(fh)}

    def lookup(self, serial: str) -> Optional[dict]:
        return self._by_serial.get(serial)


class NiseDcrClient(DcrClient):
    """To be written when NISE grants API access."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url, self.api_key = base_url, api_key

    def lookup(self, serial: str) -> Optional[dict]:
        raise NotImplementedError("NISE DCR API access not yet available")
