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
CMD ["uvicorn", "DataSpace.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
