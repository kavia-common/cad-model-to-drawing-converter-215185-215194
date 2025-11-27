"""
Pytest configuration to ensure imports like `from src.api.main import app` work
when running tests from the monorepo root or different working directories.
"""
import sys
from pathlib import Path

# Determine the backend service root (directory containing this conftest.py -> up one level)
this_file = Path(__file__).resolve()
service_root = this_file.parents[1]  # cad_backend_service
src_dir = service_root / "src"

# Prepend service root and src/ to sys.path if not already present
for p in (str(service_root), str(src_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)
