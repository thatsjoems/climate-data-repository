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

Once all three show as running, open:

- Frontend: **http://localhost:5173**
- Backend API docs: **http://localhost:8000/docs**

See `docs/DOCKER.md` for more detail (stopping, resetting data, inspecting the database).

### 2. Log In

Use one of the demo accounts printed in the `backend` container's log output:

| Role | Username | Password |
|---|---|---|
| System Admin | `admin` | `Admin@123` |
| BOT Analyst (Internal) | `bot_analyst` | `Analyst@123` |
| Institution (Bank A) | `bankA_user` | `BankA@123` |

**Change these passwords before any production use.**

### 3. After pulling updates

Whenever the backend's database models, or `docker-compose.yml` itself, have changed,
reset the database volume so the new schema is created cleanly:

```bash
docker compose down -v
docker compose up --build
```

`down -v` deletes the PostgreSQL data volume — use it whenever you are told a change
requires a fresh database. A plain `docker compose down` (no `-v`) keeps existing data.

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

This is an 8-week EASTC training prototype demonstrating the complete core workflow
(login → template → upload → validation → storage → review → dashboard) using sample data.
Production use by the Bank of Tanzania would require: real TMA/PMO data, RTIS/BSIS/QGIS/ArcGIS
access, and a full security review.
