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
# NOTE: uploads/ is a mounted named volume (see docker-compose.yml's
# cdr_uploads), not a plain image directory - a volume's on-disk ownership
# is whatever it already had (root, for any volume created before this user
# existed) and is NOT affected by this Dockerfile's own chown, since that
# only touches the image layer, before the volume is ever mounted on top of
# it. The fix has to happen at container START, not build time - see CMD
# below, which chowns the actual mounted volume, then drops to cdr to run
# the app itself. `useradd`/`mkdir`/the first `chown` below still matter:
# they cover every OTHER path under /app on a brand-new container with no
# pre-existing volume.
RUN useradd --create-home --uid 10001 cdr && \
    mkdir -p /app/uploads && \
    chown -R cdr:cdr /app

EXPOSE 8000

# On container start: fix the mounted uploads volume's ownership (root at
# this point, before USER ever applies - see note above), then run
# everything else as the unprivileged cdr user. init_db.py is safe to
# re-run - it skips seeding if data already exists.
CMD ["sh", "-c", "chown -R cdr:cdr /app/uploads && su cdr -s /bin/sh -c 'python init_db.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000'"]
