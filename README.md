# KisanProcure

SIH (Smart India Hackathon) Prototype for **Problem Statement 26032** —
Cutting waiting times, dynamic queue estimation, dynamic delays, in-app/push notifications, procurement/payment status tracking, and admin analytics at agricultural procurement centres.

---

## 🚀 Running Locally

### Prerequisites
- Python >= 3.10 (Tested on Python 3.13)
- Git

### Setup Steps
```bash
# 1. Clone & enter repository
git clone https://github.com/sanketsingh0/kishan_portal.git
cd kishan_portal

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Environment configuration (local dev uses SQLite by default)
cp .env.example .env

# 6. Apply database migrations
python -m flask --app run.py db upgrade

# 7. Seed demo data (idempotent seeder)
python -m flask --app run.py seed-demo

# 7b. Optional: seed the COMPLETE SIH demo dataset (centres, crops, staff,
#      farmers, slots, bookings, tokens, delays, procurement, payments,
#      notifications, audit logs). Also idempotent and non-destructive.
python -m flask --app run.py seed-demo-full

# 8. Start development server
python run.py
```

Visit:
- App Home: <http://127.0.0.1:5000/>
- Farmer Dashboard: <http://127.0.0.1:5000/farmer/dashboard>
- Admin Dashboard: <http://127.0.0.1:5000/admin/dashboard>
- API Health Endpoint: <http://127.0.0.1:5000/api/health>

---

## 🧪 Testing & Verification

Run unit and integration test suite:
```bash
set PYTHONPATH=.
.venv\Scripts\python.exe -m pytest -v
```

Check database migration state:
```bash
.venv\Scripts\python.exe -m flask --app run.py db check
```

---

## 🌱 Demo Seed Commands

Two idempotent seed commands are available:

### `flask seed-demo` — Basic demo data
Creates fictional demo centres and crops only. Safe to run repeatedly.

```bash
python -m flask --app run.py seed-demo
```

### `flask seed-demo-full` — Complete SIH demo dataset
Creates a full fictional demonstration dataset including:
- 2 demo procurement centres (Ludhiana Grade-A, Patiala)
- 6 demo crops (Wheat, Paddy, Maize, Gram, Soybean, Cotton)
- 2 demo staff users (one per centre)
- 5 demo farmer users
- 5 today-relative demo slots
- 5 demo bookings with sequential tokens (K-0001 … K-0005)
- Procurement, payment, delay, notification, and audit records

```bash
python -m flask --app run.py seed-demo-full
```

**Important notes:**
- All demo records are **fictional** and clearly marked.
- **No passwords are stored locally** — the seed creates local User/Staff/Farmer rows only.
- **Supabase Auth accounts must be provisioned separately** for actual login; the seed does not contact Supabase Auth and does not create fake credentials.
- **No real payment / SMS / WhatsApp / email service** is used by the seed.
- The command is **idempotent** and **non-destructive**: running it multiple times will not create duplicates or delete existing data.

### `DEMO_SEED_ON_START` — seed the full demo dataset automatically at startup (OPT-IN)

On platforms **without a Shell** (e.g. the current Render plan), the CLI
command above cannot be run manually. To get the exact same dataset
automatically during application startup, opt in via the environment:

```bash
DEMO_SEED_ON_START=true
```

It reuses the **identical** `flask seed-demo-full` implementation (no
duplicated seed logic), runs once the database/app initialization is ready,
remains idempotent and non-destructive, and:

- Defaults to **`false`** — demo seeding is **never** auto-enabled in normal production.
- Creates only fictional demo records. **No passwords, no fake JWTs, no
  Supabase Auth changes, no PostgreSQL changes** — everything the CLI seed does.
- Platform start command stays unchanged (e.g. `gunicorn -c gunicorn.conf.py run:app`).

---

## 🔑 Environment Variables

Secrets and configurations are managed via `.env` (never committed):

| Variable | Description | Default (Dev) |
|---|---|---|
| `FLASK_ENV` | Application mode (`development`, `testing`, `production`) | `development` |
| `SECRET_KEY` | Flask session signing secret | `dev-only-change-me` |
| `HOST` | Host for `python run.py` (local dev only) | `127.0.0.1` |
| `PORT` | Port for `python run.py` (local dev only) | `5000` |
| `DATABASE_URL` | SQLAlchemy URI (SQLite local / PostgreSQL production) | SQLite `instance/kisanprocure.db` |
| `SOCKETIO_ASYNC_MODE` | Socket.IO async mode — keep `threading` (only supported mode; gunicorn sync workers provide concurrency) | `threading` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed Socket.IO origins | `*` |
| `DEMO_SEED_ON_START` | `true` runs the idempotent `flask seed-demo-full` seeder automatically at startup (for platforms without a Shell, e.g. Render). Default OFF; never auto-enabled in normal production | `false` |
| `SUPABASE_URL` | Supabase project URL (safe for frontend) | Empty |
| `SUPABASE_ANON_KEY` | Supabase anonymous key (safe for frontend; legacy alias `SUPABASE_PUBLISHABLE_KEY`) | Empty |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role key (**server-only**; legacy alias `SUPABASE_SECRET_KEY`) | Empty |
| `JWT_ALGORITHM` | Algorithm used to verify Supabase JWTs | `HS256` |
| `JWT_EXP` | JWT expiry window (seconds) | `3600` |
| `VAPID_PUBLIC_KEY` | Browser Web Push Public Key | Placeholder |
| `VAPID_PRIVATE_KEY` | Browser Web Push Private Key | Placeholder |
| `VAPID_CLAIM_EMAIL` | Web Push contact email (`mailto:`) | `mailto:admin@kisanprocure.example.com` |

---

## 📱 PWA & Offline Support

KisanProcure includes a Progressive Web App (PWA) foundation:
- **Manifest**: Located at `/static/manifest.json`.
- **Service Worker**: `/static/service-worker.js` pre-caches app shell/static assets (Bootstrap, Chart.js, icons).
- **Security Rule**: Authenticated API endpoints (`/api/...`) and sensitive personal data are **never cached**.
- **Offline Fallback**: Serves `/offline` fallback page when network connection is lost.
- **PWA Installation**: Prompts users via browser install UI (`beforeinstallprompt`).

---

## ⚡ Realtime Architecture

KisanProcure uses **Flask-SocketIO** for real-time state synchronization across the `/queue` namespace:
- Real-time queue updates broadcast post-commit when bookings or queue positions change.
- In-app notification alerts emitted to specific user rooms (`farmer_user_<id>`).
- Client auto-reconnect with HTTP polling fallback.

---

## 🏭 Production & Deployment Guidelines

- **Database**: Production requires PostgreSQL (`DATABASE_URL=postgresql+psycopg://...`). SQLite is blocked in production mode.
- **Server Worker**: Deploy with **gunicorn `gthread` worker** (single multi-threaded worker) — no `eventlet`/`gevent`, no monkey-patching:

  ```
  gunicorn -c gunicorn.conf.py run:app
  ```

  A single `gthread` worker (1 process × 4 threads by default) serves both plain HTTP requests and Socket.IO WebSocket / long-poll connections. Flask-SocketIO runs in `threading` async mode, so no `eventlet`/`gevent` or monkey-patching is required. Using a single worker ensures Socket.IO room broadcasts work correctly without an external message queue (Redis/RabbitMQ). The `post_fork` hook in `gunicorn.conf.py` disposes the inherited SQLAlchemy engine pool so each worker creates its own fresh connection pool — this avoids the `RuntimeError: cannot notify on an un-acquired lock` crash in `sqlalchemy/util/queue.py` that occurs when multiple threads share a forked pool.

### Render Setup

- **Build command**: `pip install -r requirements.txt`
- **Start command**: `gunicorn -c gunicorn.conf.py run:app`
- **Python version**: 3.13 (pinned via `.python-version`)
- **Environment**: set `FLASK_ENV=production` plus the variables documented in the table above (Render auto-provides `$PORT`).
- **HTTPS & Security**: Require HTTPS for Service Worker and Web Push APIs.
- **Security Headers**: Automatic `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Cache-Control: no-store` on API responses.

---

## 📊 Feature Implementation Status

### ✅ Fully Implemented (Tasks 1–15)
- User Authentication & Role-Based Access Control (FARMER, STAFF, ADMIN)
- Farmer Profile Management
- Procurement Centre & Crop Catalogue Management
- Slot Management & Capacity Constraints
- Farmer Slot Booking & Token Generation (`K-0001`) — sequential per centre + date
- Queue Position & Estimated Wait Calculation
- Real-time Queue Updates via Socket.IO
- Procurement Tracking (Quantity & Status)
- Payment Status Tracking (Paid, Processing, Pending)
- Dynamic Delay Management (Centre-wide & Slot-specific delay calculation)
- Notification Engine (In-app alerts + Browser Web Push)
- Admin Analytics Dashboard & Chart.js Visualizations
- Append-Only Audit Logging with Sensitive Data Redaction
- PWA Foundation & Offline Fallback Page
- Production Hardening & Automated Tests Suite

### ❌ Not Implemented / Optional Future Integrations
- WhatsApp Integration
- SMS / Twilio Provider
- External Email Providers
- Third-party Payment Gateways (Razorpay / Stripe)
- Bank / UPI Integrations
- Full Offline Booking (Bookings require live backend transaction)