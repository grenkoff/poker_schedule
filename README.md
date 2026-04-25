# Poker Schedule

Aggregates online poker tournament schedules from multiple rooms
(GGNetwork, PokerDom, PokerStars, and others) into one filterable,
shareable, exportable list. Django + PostgreSQL, hosted on Railway.

## Stack

- Python 3.12 + Django 5.1
- PostgreSQL (production) / SQLite (local default)
- uv for dependency management
- Internationalized for 10 locales (en, ru, es, pt-br, de, fr, zh-hans, ja, ko, uk)
- Whitenoise for static files
- Deployed on Railway; CI via GitHub Actions

## Local setup

```bash
# Install uv (https://docs.astral.sh/uv/)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install deps and create .venv
uv sync

# Copy env template
cp .env.example .env.local

# Apply migrations
uv run python manage.py migrate

# (Optional) create superuser
uv run python manage.py createsuperuser

# Compile translations (required for non-English locales to render)
uv run python manage.py compilemessages --ignore=.venv

# Run dev server
uv run python manage.py runserver
```

Visit:

- `http://127.0.0.1:8000/` — redirects to the detected language
- `http://127.0.0.1:8000/en/` — English home page
- `http://127.0.0.1:8000/ru/` — Russian home page
- `http://127.0.0.1:8000/admin/` — Django admin
- `http://127.0.0.1:8000/healthz` — health check (used by Railway)

## Useful commands

```bash
# Lint + format
uv run ruff check .
uv run ruff format .

# Types
uv run mypy apps config

# Tests
uv run pytest

# Translations: extract new strings
uv run python manage.py makemessages -l ru --ignore=.venv

# Translations: compile .po → .mo
uv run python manage.py compilemessages --ignore=.venv
```

## Git workflow

- Never push directly to `main`.
- Create a feature branch: `git checkout -b feature/<short-name>`.
- Open a PR; CI must pass before merge.
- After merge, Railway auto-deploys `main`.

## Deployment (Railway)

Connect this GitHub repo to a Railway project. Railway reads
`railway.json` to build and run the app:

- **Build**: NIXPACKS auto-detects uv + Python 3.12, installs deps.
- **Pre-deploy**: runs `migrate`, `compilemessages`, `collectstatic`.
- **Start**: `gunicorn config.wsgi:application`.
- **Health check**: `GET /healthz` must return 200.

Required Railway environment variables:

- `DJANGO_SECRET_KEY` — random 50+ char string
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS` — your custom domain(s), comma-separated
  (`RAILWAY_PUBLIC_DOMAIN` is added automatically)
- `DATABASE_URL` — provided by the Railway Postgres plugin
- (Later) `REDIS_URL`, SMTP credentials, etc.

## Project structure

```
config/
  settings/
    base.py   # shared config, env-driven
    dev.py    # local development
    prod.py   # Railway production
  urls.py     # healthz + i18n_patterns
apps/
  users/        # custom User with timezone + preferred_language
  rooms/        # poker rooms & networks
  tournaments/  # tournament schedules & structures (admin-only entry)
  filters/      # filter presets & shared links
  exports/      # PDF export
  analytics/    # historical averages
templates/      # Django templates (base + home)
locale/         # .po/.mo translation files (10 languages)
tests/          # project-wide tests
```
