# CDR Backend - FastAPI (Python)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# On container start: ensure tables exist + demo accounts are seeded, then run the API.
# init_db.py is safe to re-run - it skips seeding if data already exists.
CMD ["sh", "-c", "python init_db.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
