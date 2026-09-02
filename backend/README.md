# CDR Backend (FastAPI)

## First-time setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

copy .env.example .env       # Windows  (macOS/Linux: cp .env.example .env)

python init_db.py            # Creates the database and loads demo accounts

uvicorn app.main:app --reload
```

The backend will be available at: http://localhost:8000
API documentation (Swagger UI): http://localhost:8000/docs

## Backend Structure

```
app/
  core/       -> config, database connection, security (JWT/hashing), RBAC guards
  models/     -> SQLAlchemy database models (tables)
  schemas/    -> Pydantic request/response validation
  api/        -> API endpoints (routes), one module per router
  services/   -> business logic (template generation, validation, analytics, audit)
```

## Database

Default: **SQLite** (`cdr.db`) — requires no setup, works immediately.

To use **PostgreSQL** instead:
1. Open the `.env` file.
2. Set `DATABASE_URL` to:
   `postgresql://postgres:YOUR_PASSWORD@localhost:5432/climate_data_repository`
3. Create the database in PostgreSQL first (via psql or pgAdmin):
   `CREATE DATABASE climate_data_repository;`
4. Re-run `python init_db.py`
