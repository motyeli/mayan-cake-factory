# Build context is the REPOSITORY ROOT, not this directory.
#
# Railway's CLI cannot set a per-service root directory, so each service is
# pointed at its Dockerfile with RAILWAY_DOCKERFILE_PATH and builds from the
# repo root. Paths below are therefore root-relative.
#
# Local equivalent, run from the repo root:
#   docker build -f backend/Dockerfile -t cake-backend .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app

# Do not run as root inside the container.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /srv
USER appuser

# Railway injects PORT. Shell form so the variable is expanded at runtime.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}
