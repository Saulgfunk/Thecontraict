"""Write the OpenAPI schema to packages/api-client/openapi.json."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

out = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else (Path(__file__).resolve().parents[3] / "packages" / "api-client" / "openapi.json")
)
out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"Wrote {out}")
