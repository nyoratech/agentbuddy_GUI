FROM python:3.12-slim

WORKDIR /app

# Build deps: gcc/libpq for psycopg2, curl/unzip for the reflex frontend toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download the reflex frontend toolchain (bun) and compile the web bundle at
# build time so container start is fast. Also scaffold alembic for migrations.
RUN reflex init || true
RUN reflex db init || true
RUN reflex export --frontend-only --no-zip || true

RUN chmod +x entrypoint.sh
EXPOSE 3000 8000

# entrypoint: migrate chat-history DB -> seed demo user -> run reflex (prod).
CMD ["./entrypoint.sh"]
