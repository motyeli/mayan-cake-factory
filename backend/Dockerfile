FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Do not run as root inside the container.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /srv
USER appuser

# Railway injects PORT. Shell form so the variable is expanded at runtime.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}
