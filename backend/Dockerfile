# CDR Backend - FastAPI (Python)
FROM python:3.12-slim

WORKDIR /app

# fonts-dejavu-core: needed for rendering readable text in the PNG dashboard-
# summary export (Module: image export) - python:3.12-slim has no TTF fonts
# by default, so PIL would otherwise fall back to a tiny, hard-to-read bitmap font.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the API as a non-root user. The upload directory is explicitly owned by
# that user because uploaded files are runtime data, not application code.
RUN useradd --create-home --uid 10001 cdr && \
    mkdir -p /app/uploads && \
    chown -R cdr:cdr /app
USER cdr

EXPOSE 8000

# On container start: ensure tables exist + demo accounts are seeded, then run the API.
# init_db.py is safe to re-run - it skips seeding if data already exists.
CMD ["sh", "-c", "python init_db.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
