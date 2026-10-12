#!/usr/bin/env bash
# Run البشرى للأخبار on this computer (macOS / Linux): ./start.sh
# Needs Python 3.11 or newer. The site opens at http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")/backend"

PY=$(command -v python3 || command -v python || true)
[ -z "$PY" ] && { echo "Python 3 is required: https://www.python.org/downloads/"; exit 1; }

if [ ! -d .venv ]; then
  echo "تثبيت المتطلبات لأول مرة..."
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

if [ -z "${ADMIN_PASSWORD:-}" ]; then
  read -r -s -p "اختر كلمة مرور لوحة الإدارة: " ADMIN_PASSWORD; echo
fi
export ADMIN_PASSWORD ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./data/albushra.db}"
export SCHEDULER_ENABLED=true
export SECRET_KEY="${SECRET_KEY:-$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 40)}"
export HDX_APP_NAME="${HDX_APP_NAME:-albushra-news}" HDX_APP_EMAIL="${HDX_APP_EMAIL:-albushra-news@users.noreply.github.com}"

echo
echo "  الموقع:  http://localhost:8000"
echo "  الإدارة: http://localhost:8000/admin   (admin / كلمة المرور التي اخترتها)"
echo "  لرابط عام يعمل على الهاتف وتطبيق أندرويد، شغّل في نافذة أخرى:"
echo "     cloudflared tunnel --url http://localhost:8000"
echo
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
