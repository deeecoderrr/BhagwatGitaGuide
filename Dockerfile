ARG PYTHON_VERSION=3.14-slim

FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# psycopg2 build deps + WeasyPrint runtime (Pango/cairo/GObject — see WeasyPrint docs).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
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

# Gevent worker class gives better concurrency for network-bound workloads
# (OpenAI/Redis/Postgres round-trips) and improves tail latency under load.
CMD ["gunicorn","--bind","0.0.0.0:8000","--worker-class","gevent","--workers","4","--worker-connections","1000","--timeout","120","--graceful-timeout","30","--keep-alive","75","config.wsgi"]
