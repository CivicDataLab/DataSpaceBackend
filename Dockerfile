FROM python:3.10
ARG GIT_COMMIT_SHA=unknown
ENV GIT_COMMIT_SHA=${GIT_COMMIT_SHA}
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && \
    apt-get autoremove -y && \
    apt-get install -y \
        curl \
        git \
        nano \
        wget \
        ca-certificates \
        fonts-liberation \
        libasound2 \
        libatk1.0-0 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libexpat1 \
        libfontconfig1 \
        libgdk-pixbuf-2.0-0 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxcursor1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxrandr2 \
        libxrender1 \
        libxss1 \
        libxtst6 \
        lsb-release \
        chromium \
        chromium-driver \
        xdg-utils && \
    rm -rf /var/lib/apt/lists/*


WORKDIR /code
COPY . /code/

# LOGGING in DataSpace/settings.py writes to logs/dataex.log -- Django's
# logging.config never creates the parent directory itself, so any fresh
# container without this (no pre-existing volume/manual mkdir) fails on
# django.setup() with FileNotFoundError before any command can even run,
# including manage.py check and the healthcheck.sh script below.
RUN mkdir -p /code/logs

RUN pip install psycopg2-binary uvicorn
RUN pip install -r requirements.txt
RUN curl -s https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js -o /code/echarts.min.js

# Create healthcheck script
RUN echo '#!/bin/bash\nset -e\npython -c "import sys; import django; django.setup(); sys.exit(0)"' > /code/healthcheck.sh \
    && chmod +x /code/healthcheck.sh


EXPOSE 8000

# Make entrypoint script executable
RUN chmod +x /code/docker-entrypoint.sh

ENTRYPOINT ["bash","/code/docker-entrypoint.sh"]

# Served with multiple workers, which is what keeps this from exhausting
# Postgres.
#
# Django runs sync views under ASGI via sync_to_async(thread_sensitive=True),
# which executes them on ONE shared thread per process. With a single worker
# that means exactly one sync request is processed at a time, no matter how
# many arrive. Measured on dev before this change: 12 concurrent calls to
# /api/auth/keycloak/login/ returned in 4s, 7s, 10s, 14s ... 36s - near-perfect
# ~3s increments, queued behind each other.
#
# That queue is what killed the database. Every in-flight request holds a
# connection while it waits its turn - measured at one connection per request,
# so 20 concurrent calls took the connection count from 6 to 26. Deep enough
# queues reached max_connections (100) and Postgres started refusing with
# "FATAL: sorry, too many clients already", which surfaced as 500s, while
# requests that waited past nginx's 60s proxy timeout surfaced as 504s. It
# also broke deploys, because manage.py could not get a connection either.
#
# Workers are processes, so N workers give N concurrent sync requests and the
# queue drains N times faster. The work here is I/O-bound (waiting on
# Keycloak), so this helps well beyond the 2 CPUs on the dev box.
#
# UVICORN_LIMIT_CONCURRENCY is the backstop: total in-flight requests are
# capped at workers x limit, which must stay under Postgres max_connections
# minus headroom for other clients. Excess requests get a fast 503 instead of
# queueing until the database runs out of slots - shedding load is recoverable,
# exhausting connections takes the deploy pipeline down with it.
# Sized to the dev box, not to a formula. One worker measured at 740MB
# resident with only ~2.4GB available on the host, so 4 workers risked an OOM
# that would have been a worse outage than the one this fixes. Two workers land
# near 1.3GB and match the 2 CPUs.
#
# Two workers alone would only double throughput, but the commit that removes
# two of the three Keycloak round-trips cuts per-request time as well, and the
# two compound. Raise UVICORN_WORKERS on a bigger box - it is env-tunable for
# exactly that reason, and worth revisiting if memory there grows.
ENV UVICORN_WORKERS=2 \
    UVICORN_LIMIT_CONCURRENCY=15

CMD ["sh", "-c", "exec uvicorn DataSpace.asgi:application --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS} --limit-concurrency ${UVICORN_LIMIT_CONCURRENCY}"]
