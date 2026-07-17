# syntax=docker/dockerfile:1.7

FROM python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64

ARG APP_UID=10001
ARG APP_GID=10001

ENV PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid "${APP_GID}" ordinarium \
    && useradd --uid "${APP_UID}" --gid ordinarium --create-home \
        --shell /usr/sbin/nologin ordinarium

WORKDIR /app

COPY containers/requirements/web.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY --chown=ordinarium:ordinarium . /app
RUN mkdir -p /app/instance && chown ordinarium:ordinarium /app/instance

USER ordinarium
EXPOSE 8080
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()"]

CMD ["gunicorn", "--bind=0.0.0.0:8080", "--workers=2", "--threads=4", "--graceful-timeout=25", "--timeout=60", "--access-logfile=-", "--error-logfile=-", "app:app"]
