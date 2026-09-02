# Climate Data Repository (CDR) — Bank of Tanzania
### Enhancement Project — EASTC 8-Week Student Practical Training Programme

This repository contains a working, end-to-end software prototype built in response to the
Bank of Tanzania Financial Stability Department's Concept Note, *"Concept Note on the
Proposed Enhancement of the Climate Data Repository."*

The prototype demonstrates the complete core workflow described in the Concept Note: secure
role-based login, standardized data template download, data upload, automated validation,
centralized repository storage, internal review by Bank of Tanzania staff, and an analytics
dashboard.

See `docs/ICN_REQUIREMENTS_TRACEABILITY_MATRIX.md` for a full mapping of Concept Note
requirements to what has been implemented, and `docs/ASSUMPTIONS_AND_LIMITATIONS.md` for a
transparent account of sample data, assumptions, and known limitations.

---

## System Overview

The system consists of two components that run together:

1. **Backend** (Python / FastAPI) — handles the database, validation, and security.
   Runs at: `http://localhost:8000`
2. **Frontend** (React / TypeScript) — the web application end users interact with.
   Runs at: `http://localhost:5173`

Both must be running at the same time, in two separate terminals, for the system to work.

---

## Getting Started

### 1. Start the Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

pip install -r requirements.txt

copy .env.example .env       # Windows  (macOS/Linux: cp .env.example .env)

python init_db.py            # Creates the database and loads demo accounts

uvicorn app.main:app --reload
```

If `uvicorn app.main:app --reload` is blocked by a Windows security policy (e.g. Device
Guard), run it via Python instead:

```bash
python -m uvicorn app.main:app --reload
```

The backend will be available at `http://localhost:8000`, with interactive API
documentation (Swagger UI) at `http://localhost:8000/docs`.

### 2. Start the Frontend (new terminal)

```bash
cd frontend
npm install
copy .env.example .env       # Windows (macOS/Linux: cp .env.example .env)
npm run dev
```

The frontend will be available at `http://localhost:5173`.

### 3. Log In

Use one of the demo accounts printed by `init_db.py`:

| Role | Username | Password |
|---|---|---|
| System Admin | `admin` | `Admin@123` |
| BOT Analyst (Internal) | `bot_analyst` | `Analyst@123` |
| Institution (Bank A) | `bankA_user` | `BankA@123` |

**Change these passwords before any production use.**

---

## Project Structure

```
climate-data-repository/
  backend/    -> FastAPI (Python) - database, API, validation, security
  frontend/   -> React (TypeScript) - web application
  database/   -> database schema documentation
  data/       -> sample / synthetic data
  docs/       -> Requirements Traceability Matrix, Assumptions & Limitations
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
