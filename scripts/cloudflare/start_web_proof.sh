#!/bin/sh
set -eu

exec gunicorn \
    --bind=0.0.0.0:8080 \
    --workers=2 \
    --threads=4 \
    --preload \
    --graceful-timeout=25 \
    --timeout=125 \
    --error-logfile=- \
    app:app
