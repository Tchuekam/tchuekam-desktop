# Process types for Heroku-style platforms (Heroku, Railway, Dokku).
#
# `web` is the SaaS API — the process that must serve concurrent end users.
# It runs tchuekam_backend (FastAPI) under gunicorn with N UvicornWorkers.
# See gunicorn.conf.py for worker/pool sizing and docs/CAPACITY.md for the
# connection budget.
#
# `web` previously started `hermes_cli.main dashboard`, the single-user
# desktop dashboard. That process spawns a TUI child per session over a PTY
# bridge, so it does not scale past one operator and it never served the
# multi-tenant API at all. The dashboard is still available below as its own
# process type.
#
# Schema migrations are NOT run here. `alembic upgrade head` belongs in a
# release/pre-deploy step: N workers booting at once would race on CREATE
# TABLE, and a failed migration must stop the deploy rather than leave every
# worker crash-looping. On Heroku that is the `release` process type below.
release: alembic upgrade head
web: gunicorn -c gunicorn.conf.py tchuekam_backend.main:app

# Single-operator desktop dashboard (PTY-backed TUI in the browser).
# Not a multi-user surface: run it on its own instance, behind authentication.
dashboard: sh -c 'INSECURE=""; case "${HERMES_DASHBOARD_INSECURE:-}" in 1|true|TRUE|yes|YES) INSECURE="--insecure" ;; esac; exec python -m hermes_cli.main dashboard --host 0.0.0.0 --port ${PORT:-8000} --skip-build --no-open $INSECURE'
