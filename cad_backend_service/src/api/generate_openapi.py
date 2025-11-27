import json
import os

from src.api.main import app

# PUBLIC_INTERFACE
def generate_openapi_file(path: str = "interfaces/openapi.json"):
    """Generate and write OpenAPI schema to interfaces/openapi.json."""
    openapi_schema = app.openapi()
    output_dir = os.path.dirname(path)
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

if __name__ == "__main__":
    generate_openapi_file()
