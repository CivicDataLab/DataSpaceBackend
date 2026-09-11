#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database..."
python << END
import sys
import time
import psycopg2
import os

# Get database connection details from environment variables
host = os.environ.get("DB_HOST", "localhost")
port = os.environ.get("DB_PORT", "5432")
dbname = os.environ.get("DB_NAME", "postgres")
user = os.environ.get("DB_USER", "postgres")
password = os.environ.get("DB_PASSWORD", "postgres")

# Try to connect to the database
start_time = time.time()
timeout = 30
while True:
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        conn.close()
        print("Database is ready!")
        break
    except psycopg2.OperationalError as e:
        if time.time() - start_time > timeout:
            print(f"Could not connect to database after {timeout} seconds: {e}")
            sys.exit(1)
        print("Waiting for database to be ready...")
        time.sleep(2)
END

# Run migrations. In the ECS pipeline this also runs earlier as an explicit
# one-off task before this service is deployed (see deploy-to-ecs.yml) so a
# broken migration fails the deploy loudly and visibly instead of surfacing
# only once containers are already shipping; this call is then a no-op
# (migrate is idempotent). Kept here unconditionally too, since this same
# entrypoint/image is what `docker compose up` uses for local dev.
echo "Running migrations..."
python manage.py migrate --noinput

# Create superuser if needed (ignore failure, e.g. if already exists)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ]; then
    echo "Creating superuser (if not exists)..."
    python manage.py createsuperuser --noinput 2>/dev/null || echo "Superuser already exists or creation skipped"
fi

# Collect static files
if [ "$COLLECT_STATIC" = "true" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# Start server
echo "Starting server..."
exec "$@"