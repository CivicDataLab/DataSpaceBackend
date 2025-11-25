FROM python:3.10
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
        xdg-utils && \
    rm -rf /var/lib/apt/lists/*


WORKDIR /code
COPY . /code/

RUN pip install psycopg2-binary uvicorn
RUN pip install -r requirements.txt

# Create healthcheck script
RUN echo '#!/bin/bash\nset -e\npython -c "import sys; import django; django.setup(); sys.exit(0)"' > /code/healthcheck.sh \
    && chmod +x /code/healthcheck.sh


EXPOSE 8000

# Make entrypoint script executable
RUN chmod +x /code/docker-entrypoint.sh

ENTRYPOINT ["/code/docker-entrypoint.sh"]
CMD ["uvicorn", "DataSpace.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
