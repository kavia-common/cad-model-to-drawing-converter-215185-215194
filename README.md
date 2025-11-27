# cad-model-to-drawing-converter-215185-215194

This monorepo contains the CAD Backend Service (FastAPI), a Postgres database container, and a React frontend.

Quick start (development):

1) Backend environment
- Copy env template and set values:
  cp cad_backend_service/.env.example cad_backend_service/.env
  - Set DATABASE_URL to your Postgres instance (or leave empty to use SQLite for local dev).
  - Set JWT_SECRET to a secure value.
  - STORAGE_DIR defaults to ./storage
  - ALLOWED_ORIGINS should include http://localhost:3000 for local frontend.

2) Seed an admin user
- Option A: via env and script (defaults are admin@example.com / Admin@12345):
  cd cad_backend_service
  python -m src.api.seed_admin
  or set:
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD=Admin@12345 python -m src.api.seed_admin

3) Run backend
- The app entry is src/api/main.py (FastAPI).
- Generate OpenAPI file when routes change:
  python -m src.api.generate_openapi
  This writes to cad_backend_service/interfaces/openapi.json.

4) Frontend environment
- Ensure cad_frontend_app/.env.development exists:
  REACT_APP_API_BASE=http://localhost:3001

5) Cypress config
- cad_frontend_app/cypress.config.js sets:
  baseUrl: http://localhost:3000

Postman
- A collection is provided at:
  cad_backend_service/tests/postman/cad-backend.postman_collection.json
- Workflow:
  Health -> Register -> Login -> Upload -> Get Job -> Downloads

OpenAPI
- The generator script uses the FastAPI app definition in src/api/main.py.
- Run: python -m src.api.generate_openapi
- Output path: cad_backend_service/interfaces/openapi.json