# Running with Docker (optional)

This is an **alternative** way to run the CDR system, alongside the manual setup
described in the main `README.md`. Both work independently — use whichever suits
the situation:

| | Manual setup (`README.md`) | Docker (`docker-compose.yml`) |
|---|---|---|
| Database | SQLite (zero config) | PostgreSQL (closer to production stack) |
| Best for | Learning, first-time setup, quick local testing | Demonstrating a more production-like deployment (e.g. Week 8 finalization) |
| Requirements | Python, Node.js installed locally | Docker Desktop only |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

## Running the full stack

From the project root (the folder containing `docker-compose.yml`):

```bash
docker compose up --build
```

This builds and starts three containers:

- `db` — PostgreSQL 16
- `backend` — FastAPI, automatically waits for the database, creates tables, and
  loads the same demo accounts as the manual setup
- `frontend` — the React app, built and served via nginx, which forwards `/api`
  requests to the backend container

Once all three show as running, open:

- Frontend: **http://localhost:5173**
- Backend API docs: **http://localhost:8000/docs**

Log in with the same demo accounts as the manual setup (see `README.md`).

## Stopping

```bash
docker compose down
```

Add `-v` (`docker compose down -v`) to also delete the PostgreSQL data volume and
start completely fresh next time.

## Notes

- The backend container reads its configuration from environment variables set
  directly in `docker-compose.yml` (not from a `.env` file) — this is normal
  Docker practice and does not affect the manual setup's `.env` file at all.
- Uploaded files persist in a named Docker volume (`cdr_uploads`) across restarts.
- To point the frontend at a differently-hosted backend, rebuild with:
  `docker compose build --build-arg VITE_API_URL=https://your-backend-url/api frontend`
