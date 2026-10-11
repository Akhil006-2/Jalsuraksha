# JalSuraksha backend notes

See the root `README.md` for the complete project setup, architecture, endpoint list, corroboration policy, and safety limitations.

## Run
```powershell
python -m pip install -r requirements-backend.txt
python -m uvicorn app.main:app --reload
```

## Validate
```powershell
python -m pytest -q
python scripts/export_openapi.py
```

The responder token is development-grade, not production authentication. Anonymous reporter tokens are pseudonymous and do not prove distinct human identities. Static susceptibility and prototype routing are not live flood intelligence.
