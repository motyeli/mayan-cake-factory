FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /srv
USER appuser

# gunicorn, not the Flask dev server. Two workers is ample for one bakery.
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --access-logfile - "app:app"
