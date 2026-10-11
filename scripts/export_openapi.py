import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.main import app

target=ROOT/"openapi"/"openapi.json"
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(app.openapi(),indent=2,ensure_ascii=False),encoding="utf-8")
print(f"OpenAPI exported to {target}")
