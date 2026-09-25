FROM python:3.11-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .

EXPOSE 8000

# Shell form (not exec form) so $PORT actually gets substituted at container
# start - Render (and similar PaaS) assign a dynamic port via that env var and
# route traffic to whatever the app is actually listening on, not to 8000.
# Falls back to 8000 when PORT isn't set (e.g. running the image directly).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
