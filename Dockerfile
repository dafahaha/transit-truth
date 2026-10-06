FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Run as an unprivileged user (S6) to reduce container-escape impact.
# The app writes its SQLite DB under /app/data, so that dir must be writable.
RUN useradd -m appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
