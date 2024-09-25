FROM python:3.10
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN echo 'deb http://archive.debian.org/debian stretch main contrib non-free' >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get autoremove -y && \
    apt-get install -y libssl1.0-dev curl git nano wget && \
    rm -rf /var/lib/apt/lists/* && rm -rf /var/lib/apt/lists/partial/*


WORKDIR /code
COPY . /code/

RUN pip install -r requirements.txt
#RUN python manage.py migrate


EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]