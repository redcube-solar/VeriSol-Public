"""VeriSol Verify: the server behind the installer app.

What it does:
  1. opens a commissioning session for one consumer, with a geo-fence around
     the registered roof
  2. accepts module serial scans only from inside the geo-fence, checks each
     against the DCR registry, and refuses any serial already held elsewhere
  3. records the array measurement
  4. locks the session: after that nothing can be changed, and the serials
     belong to that consumer
  5. offers a public look-up so anyone can check whether a module belongs to a
     subsidised roof
  6. exports locked data in the format the Validate engine reads

Run it (from the Verify folder):

    pip install -r requirements.txt
    uvicorn backend.app:app --reload

then open http://127.0.0.1:8000 on the same computer.

This is a prototype. Before any real use it needs vendor login, HTTPS and a
proper database server; see the README.
"""
from __future__ import annotations

import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .dcr_client import MockDcrClient, DcrClient

HERE = Path(__file__).resolve().parent
WEB_DIR = HERE.parent / "web"
DEFAULT_RADIUS_M = 50.0        # how far from the registered roof a scan may be made
NAMEPLATE_TOLERANCE = 0.05     # scanned modules may total up to 5 per cent under the claim

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    consumer_id TEXT NOT NULL UNIQUE,
    scheme TEXT NOT NULL,
    vendor_id TEXT NOT NULL,
    claimed_kw REAL NOT NULL,
    lat REAL NOT NULL, lon REAL NOT NULL, radius_m REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    array_length_m REAL, array_width_m REAL, tilt_deg REAL, azimuth_deg REAL,
    undertaking_at TEXT,
    created_at TEXT NOT NULL, locked_at TEXT
);
CREATE TABLE IF NOT EXISTS modules (
    serial TEXT PRIMARY KEY,              -- one serial, one roof: enforced by the database
    session_id TEXT NOT NULL REFERENCES sessions(id),
    consumer_id TEXT NOT NULL,
    manufacturer TEXT, model TEXT,
    wp REAL NOT NULL, length_m REAL, width_m REAL,
    scan_lat REAL, scan_lon REAL, scanned_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class NewSession(BaseModel):
    consumer_id: str = Field(min_length=3, max_length=40)
    scheme: str = Field(pattern="^(PMSGY|ULA)$")
    vendor_id: str = Field(min_length=1, max_length=40)
    claimed_kw: float = Field(gt=0, le=500)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: float = Field(default=DEFAULT_RADIUS_M, gt=5, le=500)


class Scan(BaseModel):
    serial: str = Field(min_length=3, max_length=60)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ArrayMeasure(BaseModel):
    length_m: float = Field(gt=0, le=100)
    width_m: float = Field(gt=0, le=100)
    tilt_deg: float = Field(ge=0, le=60)
    azimuth_deg: float = Field(ge=0, lt=360)


class LockRequest(BaseModel):
    undertaking_accepted: bool = False


def create_app(db_path: Optional[str] = None, dcr: Optional[DcrClient] = None) -> FastAPI:
    db_path = db_path or os.environ.get("VERISOL_DB", str(HERE / "verify.db"))
    dcr = dcr or MockDcrClient(os.environ.get("VERISOL_DCR_FILE", str(HERE / "sample_dcr_registry.json")))
    app = FastAPI(title="VeriSol Verify", version="0.1.0")

    def db() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    with db() as conn:
        conn.executescript(SCHEMA)

    def get_session(conn, session_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Session not found")
        return row

    def summary(conn, s: sqlite3.Row) -> dict:
        mods = conn.execute("SELECT serial, wp, manufacturer, model FROM modules WHERE session_id = ? ORDER BY scanned_at", (s["id"],)).fetchall()
        nameplate = sum(m["wp"] for m in mods) / 1000.0
        area = (s["array_length_m"] or 0) * (s["array_width_m"] or 0)
        return {
            "session_id": s["id"], "consumer_id": s["consumer_id"], "scheme": s["scheme"], "vendor_id": s["vendor_id"],
            "status": s["status"], "claimed_kw": s["claimed_kw"], "modules_scanned": len(mods),
            "nameplate_kw": round(nameplate, 3), "array_area_m2": round(area, 2) if area else None,
            "tilt_deg": s["tilt_deg"], "azimuth_deg": s["azimuth_deg"],
            "undertaking_signed": s["undertaking_at"] is not None, "locked_at": s["locked_at"],
            "modules": [dict(m) for m in mods],
        }

    @app.post("/api/sessions", status_code=201)
    def open_session(body: NewSession):
        sid = uuid.uuid4().hex[:12]
        try:
            with db() as conn:
                conn.execute(
                    "INSERT INTO sessions (id, consumer_id, scheme, vendor_id, claimed_kw, lat, lon, radius_m, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (sid, body.consumer_id.strip(), body.scheme, body.vendor_id.strip(), body.claimed_kw, body.lat, body.lon, body.radius_m, now()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "A commissioning session already exists for this consumer")
        with db() as conn:
            return summary(conn, get_session(conn, sid))

    @app.get("/api/sessions/{session_id}")
    def read_session(session_id: str):
        with db() as conn:
            return summary(conn, get_session(conn, session_id))

    @app.post("/api/sessions/{session_id}/scan", status_code=201)
    def scan_module(session_id: str, body: Scan):
        serial = body.serial.strip().upper()
        with db() as conn:
            s = get_session(conn, session_id)
            if s["status"] != "open":
                raise HTTPException(409, "This session is locked; no more modules can be added")
            away = distance_m(s["lat"], s["lon"], body.lat, body.lon)
            if away > s["radius_m"]:
                raise HTTPException(422, f"Scan refused: you are {away:.0f} m from the registered roof (limit {s['radius_m']:.0f} m)")
            rec = dcr.lookup(serial)
            if rec is None:
                raise HTTPException(422, "Serial not found on the DCR registry")
            if not rec.get("dcr_compliant", False):
                raise HTTPException(422, "Module is not DCR compliant")
            if rec.get("allotted_vendor") and rec["allotted_vendor"] != s["vendor_id"]:
                raise HTTPException(422, "Module was allotted to a different vendor on the DCR registry")
            held = conn.execute("SELECT consumer_id FROM modules WHERE serial = ?", (serial,)).fetchone()
            if held is not None:
                if held["consumer_id"] == s["consumer_id"]:
                    raise HTTPException(409, "This module has already been scanned for this roof")
                raise HTTPException(409, "Serial is already registered to another subsidised roof")
            conn.execute(
                "INSERT INTO modules (serial, session_id, consumer_id, manufacturer, model, wp, length_m, width_m, scan_lat, scan_lon, scanned_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (serial, session_id, s["consumer_id"], rec.get("manufacturer"), rec.get("model"), rec["wp"],
                 rec.get("length_m"), rec.get("width_m"), body.lat, body.lon, now()))
            return summary(conn, get_session(conn, session_id))

    @app.post("/api/sessions/{session_id}/array")
    def measure_array(session_id: str, body: ArrayMeasure):
        with db() as conn:
            s = get_session(conn, session_id)
            if s["status"] != "open":
                raise HTTPException(409, "This session is locked")
            conn.execute("UPDATE sessions SET array_length_m=?, array_width_m=?, tilt_deg=?, azimuth_deg=? WHERE id=?",
                         (body.length_m, body.width_m, body.tilt_deg, body.azimuth_deg, session_id))
            return summary(conn, get_session(conn, session_id))

    @app.post("/api/sessions/{session_id}/lock")
    def lock_session(session_id: str, body: LockRequest):
        with db() as conn:
            s = get_session(conn, session_id)
            if s["status"] != "open":
                raise HTTPException(409, "This session is already locked")
            info = summary(conn, s)
            problems = []
            if info["modules_scanned"] == 0:
                problems.append("no modules scanned")
            elif info["nameplate_kw"] < s["claimed_kw"] * (1 - NAMEPLATE_TOLERANCE):
                problems.append(f"scanned modules total {info['nameplate_kw']} kW, below the {s['claimed_kw']} kW claimed")
            if info["array_area_m2"] is None:
                problems.append("array not measured")
            if s["scheme"] == "ULA" and not body.undertaking_accepted:
                problems.append("ULA custody undertaking not accepted by the beneficiary")
            if problems:
                raise HTTPException(422, "Cannot lock: " + "; ".join(problems))
            stamp = now()
            conn.execute("UPDATE sessions SET status='locked', locked_at=?, undertaking_at=? WHERE id=?",
                         (stamp, stamp if body.undertaking_accepted else None, session_id))
            return summary(conn, get_session(conn, session_id))

    @app.get("/api/public/serial/{serial}")
    def public_lookup(serial: str):
        """Anyone may check a serial. No consumer or vendor details are revealed."""
        with db() as conn:
            row = conn.execute(
                "SELECT s.scheme FROM modules m JOIN sessions s ON s.id = m.session_id WHERE m.serial = ? AND s.status = 'locked'",
                (serial.strip().upper(),)).fetchone()
        if row is None:
            return {"serial": serial.strip().upper(), "on_subsidised_roof": False}
        return {"serial": serial.strip().upper(), "on_subsidised_roof": True,
                "message": "This module is registered to a government-supported rooftop system and must not be bought, sold or moved."}

    @app.get("/api/export")
    def export_for_validate():
        """Locked sessions in the shape of Validate's installations.csv and dcr_modules.csv."""
        with db() as conn:
            sessions = conn.execute("SELECT * FROM sessions WHERE status = 'locked'").fetchall()
            mods = conn.execute("SELECT m.*, s.vendor_id FROM modules m JOIN sessions s ON s.id = m.session_id WHERE s.status = 'locked'").fetchall()
        return {
            "installations": [{
                "consumer_id": s["consumer_id"], "scheme": s["scheme"], "vendor_id": s["vendor_id"], "claimed_kw": s["claimed_kw"],
                "lat": s["lat"], "lon": s["lon"], "tilt_deg": s["tilt_deg"], "pre_solar_kwh": "",
                "commissioned_on": (s["locked_at"] or "")[:10], "scanned_on_roof": 1, "fault_logged": "",
                "array_area_m2": round(s["array_length_m"] * s["array_width_m"], 2),
            } for s in sessions],
            "dcr_modules": [{
                "serial": m["serial"], "consumer_id": m["consumer_id"], "vendor_id": m["vendor_id"],
                "wp": m["wp"], "length_m": m["length_m"], "width_m": m["width_m"],
            } for m in mods],
        }

    @app.get("/")
    def home():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")
    return app


app = create_app()
