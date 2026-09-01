# CDR Backend (FastAPI)

## Kuanzisha kwa mara ya kwanza

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

copy .env.example .env       # Windows  (Mac/Linux: cp .env.example .env)

python init_db.py            # Inatengeneza database na kuweka watumiaji wa DEMO

uvicorn app.main:app --reload
```

Backend itapatikana kwenye: http://localhost:8000
API documentation (Swagger) moja kwa moja: http://localhost:8000/docs

## Muundo wa Backend

```
app/
  core/       -> config, database connection, security (JWT/hashing), RBAC guards
  models/     -> SQLAlchemy database models (majedwali)
  schemas/    -> Pydantic request/response validation
  api/        -> API endpoints (routes), kimoja kwa kila module
  services/   -> business logic (template generation, validation, analytics, audit)
```

## Database

Default: **SQLite** (`cdr.db`) - haihitaji usanidi wowote, inafanya kazi mara moja.

Ukitaka kutumia **PostgreSQL** uliyosakinisha:
1. Fungua faili `.env`
2. Badilisha `DATABASE_URL` iwe:
   `postgresql://postgres:PASSWORD_YAKO@localhost:5432/climate_data_repository`
3. Tengeneza database kwenye PostgreSQL kwanza (kwa psql au pgAdmin):
   `CREATE DATABASE climate_data_repository;`
4. Endesha tena `python init_db.py`
