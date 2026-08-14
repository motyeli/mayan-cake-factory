# Build context is the REPOSITORY ROOT — see backend/Dockerfile for why.
#
# Local equivalent, run from the repo root:
#   docker build -f frontend/Dockerfile -t cake-frontend .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/app.py .
COPY frontend/templates ./templates
COPY frontend/static ./static

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /srv
USER appuser

# gunicorn, not the Flask dev server. Two workers is ample for one bakery.
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --access-logfile - "app:app"
