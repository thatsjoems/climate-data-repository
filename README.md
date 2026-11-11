# Climate Data Repository (CDR) — Bank of Tanzania
### Enhancement Project — EASTC 8-Week Student Practical Training Programme

This repository contains a working, end-to-end software prototype built in response to the
Bank of Tanzania Financial Stability Department's Concept Note, *"Concept Note on the
Proposed Enhancement of the Climate Data Repository."*

The prototype demonstrates the complete core workflow described in the Concept Note: secure
role-based login, standardized data template download, data upload, automated validation,
centralized repository storage, internal review by Bank of Tanzania staff, climate data
ingestion, geospatial visualization, and analytics dashboards.

See `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md` for a full mapping of Concept Note
requirements to what has been implemented, and `docs/ASSUMPTIONS_AND_LIMITATIONS.md` for a
transparent account of sample data, assumptions, and known limitations.

---

## System Overview

The system consists of three components, all run together with Docker:

1. **Database** (PostgreSQL 16) — the same class of database BOT's own Climate Data
   Repository uses (see the Report on Climate Risk Analysis in the Banking Sector, March 2026).
2. **Backend** (Python / FastAPI) — handles the database, validation, and security.
   Reachable at: `http://localhost:8000` (API docs at `/docs`).
3. **Frontend** (React / TypeScript) — the web application end users interact with.
   Reachable at: `http://localhost:5173`.

Sign-in links for every environment (development, staging, production) are on one page: [`docs/LOGIN_LINKS.md`](docs/LOGIN_LINKS.md).

Docker is the **only** supported way to run this project — there is no separate manual/local
Python+Node setup to maintain, which keeps the environment identical for every developer.

---

## Getting Started

### Prerequisite

[Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running,
with an internet connection (needed the first time, to download base images).

### 1. Start everything

From the project root (the folder containing `docker-compose.yml`):

```bash
docker compose up --build
```

This builds and starts three containers — `db` (PostgreSQL), `backend` (FastAPI), and
`frontend` (the React app, served via nginx). The backend automatically waits for the
database, creates tables, and loads demo accounts on first run.

Once all three show as running, open the sign-in page that matches your account
(details in step 2):

- Institution users: **http://localhost:5173/login**
- BOT staff and administrators: **http://localhost:5173/staff/login**
- Backend API documentation (development only): http://localhost:8000/docs

See `docs/DOCKER.md` for more detail (stopping, resetting data, inspecting the database).

### 2. Log In - Two Separate Sign-in Pages

The system has two sign-in pages, one for each kind of user. An account cannot sign in on
the other page; a wrong choice gives the same message, "Incorrect username or password".

| User type | Sign-in link (development) | Demo account |
|---|---|---|
| **Institution user** (bank or other reporting institution) | http://localhost:5173/login | `bankA_user` / `BankA@123`<br>`bankB_user` / `BankB@123` |
| **BOT analyst** | http://localhost:5173/staff/login | `bot_analyst` / `Analyst@123` |
| **System administrator** | http://localhost:5173/staff/login | `admin` / `Admin@123` |

Forgot password (both user types): http://localhost:5173/forgot-password

> **DEVELOPMENT AND TRAINING ONLY.** The accounts above exist only in the development stack
> (`docker-compose.yml`), with passwords that are written in this file and therefore known to
> anyone who reads it. They are never created in staging or production, and must never be
> created, copied or recreated there. Do not use them anywhere other than your own
> development machine.

Links for staging and production are on one page: [`docs/LOGIN_LINKS.md`](docs/LOGIN_LINKS.md).

In production (`ENVIRONMENT=production`) the demo accounts are **not created at all**; create
the first administrator with `scripts/create_admin.py` - see
[`docs/DATABASE_OPERATIONS.md`](docs/DATABASE_OPERATIONS.md), section 3, which also covers backups.

### 3. After pulling updates

Rebuild and restart. The database schema is brought up to date automatically - the backend
runs its migrations (`alembic upgrade head`) every time it starts - and **your data is kept**:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose exec backend pytest -v
```

**Do not use `docker compose down -v` on a system that holds real data.** `-v` deletes the
database *and* the uploaded files. It is only for a throw-away demo or training copy when you
really do want to start from nothing. If in doubt, take a backup first - see
[`docs/DATABASE_OPERATIONS.md`](docs/DATABASE_OPERATIONS.md).

> Earlier versions of this README said to reset the volume whenever the models or
> `docker-compose.yml` changed. That predates the migrations and is no longer needed.

---

## Running Tests

```bash
docker compose exec backend pytest -v
```

(Run this while `docker compose up` is already running in another terminal.) Tests use an
isolated in-memory database and never touch the real containerized database or demo data.
See `docs/SECURITY_HARDENING.md` for what's covered.

## Sharing with Other Devices on Your Network

Docker's port mapping already listens on all of your computer's network interfaces by
default, so this typically works with no extra configuration — see `docs/NETWORK_ACCESS.md`.
For access from anywhere on the internet, the system needs to be deployed to a real hosting
server — this is tracked as outstanding in `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md`.

---

## Project Structure

```
climate-data-repository/
  backend/    -> FastAPI (Python) - database, API, validation, security
  frontend/   -> React (TypeScript) - web application
  database/   -> database schema documentation
  data/       -> sample / synthetic data
  docs/       -> Requirements Traceability Matrix, Assumptions & Limitations
  docker-compose.yml -> the only way this project is run
```

Further technical detail:
- `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md` — which Concept Note requirements are
  implemented, which are outstanding, and why.
- `docs/ASSUMPTIONS_AND_LIMITATIONS.md` — what is sample/synthetic data, and what could not
  be built due to lack of access (RTIS, BSIS, QGIS, ArcGIS, TMA, PMO).
- `backend/README.md` and `frontend/README.md` — component-level technical documentation.

## Rate Limiting

Enforced via `slowapi` (`backend/app/core/rate_limit.py`):
- **Default (every endpoint):** 200 requests/minute per IP address.
- **`POST /auth/login`:** 10 requests/minute per IP address — tighter, to slow down
  password-guessing attempts specifically, independent of the global default above.

A request over the limit receives HTTP 429. These are per-IP, not per-user, and reset on a
rolling one-minute window.

This is an 8-week EASTC training prototype demonstrating the complete core workflow
(login → template → upload → validation → storage → review → dashboard) using sample data.
Production use by the Bank of Tanzania would require: real TMA/PMO data, RTIS/BSIS/QGIS/ArcGIS
access, and a full security review.
