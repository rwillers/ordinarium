#!/bin/sh
set -eu

if [ "${ORDINARIUM_DISPOSABLE_SQLITE:-false}" = "true" ]; then
    flask --app ordinarium init-db
fi

exec gunicorn \
    --bind=0.0.0.0:8080 \
    --workers=2 \
    --threads=4 \
    --graceful-timeout=25 \
    --timeout=60 \
    --access-logfile=- \
    --error-logfile=- \
    app:app
