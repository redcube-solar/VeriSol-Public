# Verify: the installer app

A small server (`backend/`) and a phone-friendly web page (`web/`).

```
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Then open http://127.0.0.1:8000.

What the server enforces:

- a scan is accepted only within 50 m of the registered roof
- the serial must be on the DCR registry, DCR compliant, and not allotted to a different vendor
- a serial can belong to one roof only (a database rule, not just a check)
- a session cannot be locked until the scanned modules add up to the claimed kW and the array is measured
- a ULA session also needs the beneficiary's custody undertaking
- after locking, nothing can be changed

Before real use this needs: vendor login (there is none yet, so anyone who can reach the server can open a session), HTTPS, a database server in place of the SQLite file, the real NISE DCR API in `backend/dcr_client.py`, and protection against faked GPS. The web page has been checked for errors but has not yet been tried on a phone on a rooftop.
