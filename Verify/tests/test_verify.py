import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from backend.app import create_app, distance_m

ROOF = {"lat": 20.2961, "lon": 85.8245}
NEAR = {"lat": 20.29612, "lon": 85.82452}     # a few metres away
FAR = {"lat": 20.3061, "lon": 85.8245}        # about 1.1 km away


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def open_session(client, consumer="C100", scheme="PMSGY", kw=1.08, vendor="V01"):
    r = client.post("/api/sessions", json={"consumer_id": consumer, "scheme": scheme, "vendor_id": vendor, "claimed_kw": kw, **ROOF})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def scan(client, sid, serial, where=NEAR):
    return client.post(f"/api/sessions/{sid}/scan", json={"serial": serial, **where})


def test_distance():
    assert 1000 < distance_m(ROOF["lat"], ROOF["lon"], FAR["lat"], FAR["lon"]) < 1200


def test_full_commissioning_and_lock(client):
    sid = open_session(client)
    assert scan(client, sid, "DEMO5400001").status_code == 201
    assert scan(client, sid, "demo5400002").json()["nameplate_kw"] == 1.08
    assert client.post(f"/api/sessions/{sid}/array", json={"length_m": 2.3, "width_m": 2.3, "tilt_deg": 15, "azimuth_deg": 180}).status_code == 200
    locked = client.post(f"/api/sessions/{sid}/lock", json={})
    assert locked.status_code == 200 and locked.json()["status"] == "locked"
    assert scan(client, sid, "DEMO5400003").status_code == 409            # nothing can be added after lock
    assert client.get("/api/public/serial/DEMO5400001").json()["on_subsidised_roof"] is True
    assert client.get("/api/public/serial/DEMO5400009").json()["on_subsidised_roof"] is False
    out = client.get("/api/export").json()
    assert out["installations"][0]["consumer_id"] == "C100" and len(out["dcr_modules"]) == 2


def test_scan_outside_geofence_is_refused(client):
    sid = open_session(client)
    r = scan(client, sid, "DEMO5400001", FAR)
    assert r.status_code == 422 and "from the registered roof" in r.json()["detail"]


def test_serial_cannot_be_used_on_two_roofs(client):
    a = open_session(client, "C101")
    b = open_session(client, "C102")
    assert scan(client, a, "DEMO5400005").status_code == 201
    r = scan(client, b, "DEMO5400005")
    assert r.status_code == 409 and "another subsidised roof" in r.json()["detail"]


def test_unknown_non_dcr_and_wrong_vendor_modules_are_refused(client):
    sid = open_session(client)
    assert scan(client, sid, "NOTAREALSERIAL").status_code == 422
    assert scan(client, sid, "DEMOIMPORT0001").status_code == 422
    assert scan(client, sid, "DEMOVENDOR0001").status_code == 422


def test_cannot_lock_when_scanned_modules_fall_short_of_claim(client):
    sid = open_session(client, kw=3.24)
    scan(client, sid, "DEMO5400001"); scan(client, sid, "DEMO5400002")
    client.post(f"/api/sessions/{sid}/array", json={"length_m": 2.3, "width_m": 2.3, "tilt_deg": 15, "azimuth_deg": 180})
    r = client.post(f"/api/sessions/{sid}/lock", json={})
    assert r.status_code == 422 and "below the 3.24 kW claimed" in r.json()["detail"]


def test_ula_needs_the_custody_undertaking(client):
    sid = open_session(client, scheme="ULA")
    scan(client, sid, "DEMO5400001"); scan(client, sid, "DEMO5400002")
    client.post(f"/api/sessions/{sid}/array", json={"length_m": 2.3, "width_m": 2.3, "tilt_deg": 15, "azimuth_deg": 180})
    assert client.post(f"/api/sessions/{sid}/lock", json={}).status_code == 422
    ok = client.post(f"/api/sessions/{sid}/lock", json={"undertaking_accepted": True})
    assert ok.status_code == 200 and ok.json()["undertaking_signed"] is True


def test_one_session_per_consumer(client):
    open_session(client, "C107")
    r = client.post("/api/sessions", json={"consumer_id": "C107", "scheme": "PMSGY", "vendor_id": "V01", "claimed_kw": 1, **ROOF})
    assert r.status_code == 409


def test_home_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "VeriSol" in r.text
    assert client.get("/web/app.js").status_code == 200


def test_two_thousand_modules_across_five_hundred_roofs(client):
    """The sample registry holds 2,000 modules. Commission all of them, four to a roof."""
    for roof in range(500):
        sid = open_session(client, consumer=f"BULK{roof:04d}", kw=2.16)
        for k in range(4):
            assert scan(client, sid, f"DEMO540{roof * 4 + k + 1:04d}").status_code == 201
        client.post(f"/api/sessions/{sid}/array", json={"length_m": 4.6, "width_m": 2.3, "tilt_deg": 15, "azimuth_deg": 180})
        assert client.post(f"/api/sessions/{sid}/lock", json={}).status_code == 200
    # every module is now tied to one roof and cannot be claimed again
    sid = open_session(client, consumer="BULKLATE", kw=1.08)
    assert scan(client, sid, "DEMO5402000").status_code == 409
    assert client.get("/api/public/serial/DEMO5401234").json()["on_subsidised_roof"] is True
