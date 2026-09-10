# CDR Backend (FastAPI)

This backend is run exclusively via Docker Compose from the project root — see the main
`README.md` and `docs/DOCKER.md`. There is no separate manual/local setup path.

To run backend-only commands (e.g. tests) against the running Docker environment:

```bash
docker compose exec backend pytest -v
docker compose exec backend python -c "from app.core.config import settings; print(settings.DATABASE_URL)"
```

## Backend Structure

```
app/
  core/       -> config, database connection, security (JWT/hashing), RBAC guards
  models/     -> SQLAlchemy database models (tables)
  schemas/    -> Pydantic request/response validation
  api/        -> API endpoints (routes), one module per router
  services/   -> business logic (template generation, validation, analytics, audit,
                 climate data ingestion, report generation)
```

## Database

PostgreSQL 16, provisioned automatically by `docker-compose.yml` (see the `db` service).
Connection details are read from environment variables set in `docker-compose.yml` / a
`.env` file next to it — see `.env.docker.example` at the project root for what to
override before any real deployment (database password, `SECRET_KEY`, etc.).
