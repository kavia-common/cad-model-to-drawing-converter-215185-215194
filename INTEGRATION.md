Integration overview

- Backend (.env)
  - DATABASE_URL=<set for Postgres from cad_database> or leave empty to use SQLite fallback
  - JWT_SECRET=<secure secret>
  - STORAGE_DIR=./storage
  - ALLOWED_ORIGINS=http://localhost:3000

- Frontend (.env.development)
  - REACT_APP_API_BASE=http://localhost:3001

- Cypress (cypress.config.js)
  - baseUrl: http://localhost:3000

- Postman
  - Collection: cad_backend_service/tests/postman/cad-backend.postman_collection.json
  - Use order: Health -> Register -> Login -> Upload -> Jobs -> Downloads

- Seeding Admin
  - Run: python -m src.api.seed_admin
  - Optional env: ADMIN_EMAIL, ADMIN_PASSWORD
  - Or set SEED_ADMIN=true to seed on backend startup.

- OpenAPI
  - Generate: python -m src.api.generate_openapi
  - Output: cad_backend_service/interfaces/openapi.json
