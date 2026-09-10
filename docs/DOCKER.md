# Running with Docker

Docker is the **only** supported way to run this project — see the main `README.md`.
There is no separate manual/local Python+Node setup to maintain.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
- An internet connection (needed the first time, to download base images).

## Running the full stack

From the project root (the folder containing `docker-compose.yml`):

```bash
docker compose up --build
```

This builds and starts three containers:

- `db` — PostgreSQL 16
- `backend` — FastAPI, automatically waits for the database, creates tables, and
  loads demo accounts on first run
- `frontend` — the React app, built and served via nginx, which forwards `/api`
  requests to the backend container

Once all three show as running, open:

- Frontend: **http://localhost:5173**
- Backend API docs: **http://localhost:8000/docs**

Log in with the demo accounts listed in `README.md`.

## Stopping

```bash
docker compose down
```

Add `-v` (`docker compose down -v`) to also delete the PostgreSQL data volume and
start completely fresh next time. **Use `-v` whenever you've pulled an update that
changes database models, adds tables, or changes `docker-compose.yml` itself** — the
project's database schema is created fresh on an empty database, not migrated.

## Inspecting the database directly

```bash
docker exec -it climate-data-repository-db-1 psql -U postgres -d climate_data_repository
```

Then, inside `psql`: `\dt` lists all tables; `SELECT count(*) FROM submissions;` (or any
table) runs a query; `\q` exits.

## Running backend commands (e.g. tests)

```bash
docker compose exec backend pytest -v
```

## Notes

- The backend container reads its configuration from environment variables set in
  `docker-compose.yml`, with sensible development-only defaults. Before any real
  deployment, create a `.env` file next to `docker-compose.yml` (copy
  `.env.docker.example`) with your own database password and `SECRET_KEY` — see the
  comments at the top of `docker-compose.yml`.
- Uploaded files persist in a named Docker volume (`cdr_uploads`) across restarts.
- PostgreSQL inside Docker is reachable from your own computer on **port 5433**
  (not 5432) — e.g. if you want to inspect it with pgAdmin or DBeaver instead of `psql`.
- To point the frontend at a differently-hosted backend, rebuild with:
  `docker compose build --build-arg VITE_API_URL=https://your-backend-url/api frontend`
