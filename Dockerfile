ARG PYTHON_VERSION=3.14-slim

FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install psycopg2 dependencies.
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /code

WORKDIR /code

COPY requirements.txt /tmp/requirements.txt
RUN set -ex && \
    pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt && \
    rm -rf /root/.cache/
COPY . /code

RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Give the LLM a bit more time on cold starts / transient latency so workers
# don't get SIGABRT mid-request (which leads to partial HTML responses).
CMD ["gunicorn","--bind",":8000","--workers","2","--timeout","120","--graceful-timeout","30","--keep-alive","5","config.wsgi"]
