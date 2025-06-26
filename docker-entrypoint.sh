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

# Ensure migrations directory exists with proper permissions
echo "Ensuring migrations directory exists..."
mkdir -p /code/api/migrations
chmod -R 777 /code/api/migrations
touch /code/api/migrations/__init__.py

# Run makemigrations first to ensure migration files are created
echo "Running makemigrations..."
python manage.py makemigrations --noinput

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Create superuser if needed
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ] && [ "$DJANGO_SUPERUSER_EMAIL" ]; then
    echo "Creating superuser..."
    python manage.py createsuperuser --noinput
fi

# Collect static files
if [ "$COLLECT_STATIC" = "true" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# Start server
echo "Starting server..."
exec "$@"
