# KisanProcure

SIH (Smart India Hackathon) prototype for **Problem Statement 26032** —
cutting waiting times and improving communication at agricultural
procurement centres.

## What problem does it solve?

| Pain point | What the system addresses |
|---|---|
| Long waiting times at centres | Booked time slots + queue position + live queue tracking |
| No visibility of the schedule | Crop- and centre-wise slot availability, time-slot booking |
| Uncertain queue / procurement status | Unique token, farmers-ahead count, live status |
| Poor delay and turn communication | Centre delay alerts, "your turn" notifications |

## Current status

**Foundation milestone (v0.1.0) — application skeleton only.**

Working today: project structure, configuration system, Flask app factory,
SQLAlchemy + Flask-Migrate + Flask-SocketIO + APScheduler wiring, an API
health check, a placeholder landing page, pytest smoke tests, Git history.

Not yet implemented (by design — built in later milestones): authentication,
roles, crops/centres, slots, booking, tokens, queue, realtime events,
procurement, payments, notifications, push, analytics, audit logs, PWA.

## Technology stack (locked)

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js, PWA/Service Worker |
| Backend | Python 3, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-SocketIO |
| Realtime | Flask-SocketIO (primary); Supabase Realtime stays optional/future |
| Scheduling | APScheduler (reminders, expired slots, notifications) |
| Database | SQLite for local dev / Supabase PostgreSQL in production |
| Auth | Supabase Auth (JWT), role checks enforced in backend routes |
| Notifications | In-app + push (free channels); WhatsApp/SMS optional/future |
| Tests | Pytest |

Zero-cost orientation: no paid services, no mandatory external APIs.

## Architecture

```
                    ┌────────────────────────────┐
                    │      Flask (app factory)     │
                    │  routes → services → models  │
                    └─────────────┬──────────────┘
        ┌──────────────┬──────────┴──────────┬──────────────┐
   Flask-SocketIO  APScheduler  SQLAlchemy   Notification   Supabase Auth
   (realtime)      (jobs)       (Postgres/     Engine         (JWT)
                                 SQLite)   ├ In-App / Push
                                            └ optional WhatsApp/SMS
```

Extensions (`db`, `migrate`, `socketio`, `scheduler`) live in
`app/extensions.py` to avoid circular imports.

## Project layout

```
sih/
├── app/
│   ├── __init__.py            # application factory
│   ├── extensions.py          # db, migrate, socketio, scheduler
│   ├── models/                # future DB models (per domain)
│   ├── routes/                # API blueprints (/api/health, ...)
│   ├── services/              # business logic services
│   ├── auth/                  # Supabase Auth integration (future)
│   ├── notifications/         # channel-agnostic notification engine (future)
│   ├── queue/                 # queue + realtime logic (future)
│   ├── templates/             # Jinja2 templates (placeholder page now)
│   └── static/                # CSS/JS/images
├── migrations/                # Flask-Migrate / Alembic (post `db init`)
├── tests/                     # pytest suite
├── config.py                  # development / testing / production configs
├── run.py                     # dev entry point
├── requirements.txt
├── pytest.ini
├── .env.example               # env template (placeholders only)
└── .gitignore
```

## Getting started

Prerequisites: Python >= 3.10 (developed on 3.13).

```bash
# 1. create a virtual environment
python -m venv .venv

# 2. activate
#    Windows PowerShell:
.venv\Scripts\Activate.ps1
#    Linux / macOS:
# source .venv/bin/activate

# 3. install dependencies
pip install -r requirements.txt

# 4. configure environment (optional for local dev - SQLite is the default)
copy .env.example .env         # Windows
cp .env.example .env           # Linux/macOS

# 5. run the app
python run.py
```

Then visit:

- App: <http://127.0.0.1:5000/>
- Health check: <http://127.0.0.1:5000/api/health>

Expected health response:

```json
{
  "status": "ok",
  "service": "KisanProcure API",
  "version": "0.1.0",
  "environment": "development",
  "database": "ok",
  "timestamp": "2026-01-01T00:00:00+00:00"
}
```

### Running the tests

```bash
pytest
pytest --cov=app --cov-report=term-missing   # coverage report
```
### Database migrations

Local development uses SQLite automatically; no setup required.
To use Supabase PostgreSQL in production, set `DATABASE_URL`:

```
postgresql+psycopg://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

Manage schema with Flask-Migrate:

```bash
flask --app run.py db init      # one-time: creates migrations/
flask --app run.py db migrate -m "phase 1 models"
flask --app run.py db upgrade
```

### Demo seed data

Insert clearly fictional development data (sample centres + crops) with:

```bash
flask --app run.py seed-demo
```

The seeder is idempotent - running it repeatedly never duplicates records.

## Database schema (Phase 1)

| Table | Purpose | Key relationships / constraints |
|---|---|---|
| `users` | Accounts for FARMER / STAFF / ADMIN. `supabase_user_id` mirrors Supabase Auth. No passwords stored. | role CHECK-constrained, is_active, unique `supabase_user_id` |
| `farmers` | Minimal farmer profile (name, phone, address fields) | 1:1 `user_id` → users.id (unique), `phone` unique |
| `staff` | Centre staff profile | 1:1 `user_id` → users.id (unique), optional `centre_id` → centres.id |
| `centres` | Procurement centres; `average_processing_minutes` feeds later waiting-time estimates | unique `name`, operating hours, daily capacity, is_active |
| `crops` | Procurable crop catalogue | unique `name`, optional category, is_active |

All tables carry `created_at` / `updated_at` timestamps (UTC).
Phase 1 only - slots, bookings, queue, procurement and notifications come in later milestones.

## Configuration

All secrets come from environment variables (see `.env.example`). Never
commit `.env`. Key variables:

| Variable | Purpose |
|---|---|
| `FLASK_ENV` | `development` / `testing` / `production` |
| `SECRET_KEY` | session signing (required in production) |
| `DATABASE_URL` | SQLAlchemy URL; empty = local SQLite (dev) |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase Auth (used from the auth milestone onward) |
| `JWT_ALGORITHM` / `JWT_EXP` | Supabase token verification settings |
| `SOCKETIO_ASYNC_MODE` | `threading` (dev) / `eventlet` / `gevent` |

## Roadmap / development order

1. Foundation (this milestone) ✔
2. Configuration ✔ · App factory ✔ · Health check ✔
3. Database models → 4. Migrations → 5. Authentication → 6. Role
   authorization → 7. Farmer module → 8. Crops/centres → 9. Slot management
   → 10. Booking → 11. Token generation → 12. Queue system → 13. SocketIO
   realtime → 14. Procurement → 15. Payment status → 16. In-app
   notifications → 17. Push notifications → 18. Delay management → 19. Admin
   analytics → 20. Audit logs → 21. PWA → 22. Testing → 23. Deployment
   (PWA is added after the core web app works, never earlier.)

## Security notes

- Secrets live only in environment variables; `.env` is gitignored.
- Backend validates and authorises every operation; roles are never trusted
  from the client.
- ORM (SQLAlchemy) used for all queries — no string-built SQL.
- Supabase Row Level Security (RLS) applied per table where appropriate.
- Fail-fast production checks (missing `DATABASE_URL` / weak `SECRET_KEY`
  abort startup).

## Deployment notes

- Dev server: `python run.py` (Windows/macOS/Linux).
- Linux production: `gunicorn -w 2 "run:app"` (gunicorn does not run on
  Windows).
- Realtime in production: run under an async-capable server (eventlet /
  gevent) via `SOCKETIO_ASYNC_MODE`.
- Apply migrations with `flask --app run.py db upgrade`.#   k i s h a n _ p o r t a l  
 