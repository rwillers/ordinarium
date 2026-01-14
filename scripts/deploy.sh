#!/usr/bin/env bash
set -euo pipefail

cd /srv/ordinarium
git pull

if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
  pip install -r requirements.txt
  python scripts/migrate_db.py
fi

sudo systemctl restart ordinarium
