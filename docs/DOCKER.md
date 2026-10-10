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

**Run the tests on the development stack only, never inside production or staging.** They are written for the development settings (two-step
sign-in off, a writable uploads folder). Inside production they fail for the right reasons, not because of a defect: two-step sign-in is required for
staff (so a test that signs in as an analyst or administrator gets no full token and the next request is refused with 401), and the hardening of the
container (`cap_drop: ALL`, `docs/DOCKER.md` above) means `docker compose exec` as root cannot write to the uploads folder that belongs to the
application's user (`PermissionError: ... 'uploads/...'`). On the first run in production this gave 209 failures and 27 errors, none of them a code
defect (the same code passes on the development stack). The tests use an in-memory database, so production's data was not touched.

To check production after `prod_up`, use its own checks (they read, never write):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/verify_db_constraints.py
docker compose -f docker-compose.prod.yml --env-file .env.production exec backend python scripts/system_check.py
curl.exe -k https://localhost/api/health
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


## Container hardening (production and staging)

`docker-compose.prod.yml` limits what the application and the web server can do if one of them is ever taken over:

| Service | `no-new-privileges` | Capabilities kept (everything else is dropped) | Why those |
|---|---|---|---|
| backend | yes | `CHOWN`, `SETUID`, `SETGID` | The start-up gives the uploads volume to the application's own user and then runs the application as that user (`cdr`, uid 10001). |
| frontend (nginx) | yes | `NET_BIND_SERVICE`, `CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE` | Ports 80 and 443; handing its temporary folders to its worker user; reading the certificate key, which on a Linux server is often readable only by its owner (nginx starts as root). |
| db | not set | Docker's defaults | The database image needs several more; changing it risks the data for little gain. A decision for the Bank. |

Not done, deliberately: a read-only root file system (the report generators, the PDF and the chart libraries write cache files, and nothing here can prove they all cope); running the container as a non-root user from its first process (the volume's owner must be fixed first). Both are possible later with a test of every report and export.

The production checker (`scripts/check_production_config.py`) refuses a compose file that loses these lines for the backend or the web server.

**To check on a running stack** (staging first):

    docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging ps
    docker inspect cdr-staging-backend-1 --format "{{.HostConfig.SecurityOpt}} drop={{.HostConfig.CapDrop}} add={{.HostConfig.CapAdd}}"

All services must be `healthy`, and then the load test (`LOAD_TESTING.md`, a short run) and a report download show the application still works as the unprivileged user.

**What this changes for the person at the keyboard.** `docker compose exec` gives a shell as root, and root no longer has the capability that lets it write anywhere regardless of ownership. The application's own folder (`/app/uploads`) belongs to the user `cdr`. So a command that reads or writes FILES there must run as that user: add `-u cdr` after `exec`. Today that means only the load-test tool (`exec -u cdr backend python scripts/load_test.py ...`, `LOAD_TESTING.md`). Commands that only talk to the database (`create_admin.py`, `reset_password.py`, `reset_mfa.py`, `db_diagnose.py`, `verify_db_constraints.py`, `system_check.py`) are not affected. If the load-test tool says "Not set up yet" although `setup` was run, this is the reason, and its message says so.
