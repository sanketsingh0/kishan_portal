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

## 🔑 Environment Variables

Secrets and configurations are managed via `.env` (never committed):

| Variable | Description | Default (Dev) |
|---|---|---|
| `FLASK_ENV` | Application mode (`development`, `testing`, `production`) | `development` |
| `SECRET_KEY` | Flask session signing secret | `dev-only-change-me` |
| `HOST` | Host for `python run.py` (local dev only) | `127.0.0.1` |
| `PORT` | Port for `python run.py` (local dev only) | `5000` |
| `DATABASE_URL` | SQLAlchemy URI (SQLite local / PostgreSQL production) | SQLite `instance/kisanprocure.db` |
| `SOCKETIO_ASYNC_MODE` | Socket.IO engine mode (`threading`, `eventlet`, `gevent`) | `threading` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed Socket.IO origins | `*` |
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
- **Server Worker**: Deploy using an async Socket.IO server (e.g. `gunicorn -k eventlet -w 1 "run:app"`). `gunicorn` is pinned in `requirements.txt` for Linux only; the `eventlet`/`gevent` worker is **not** pinned, so install the worker package that matches `SOCKETIO_ASYNC_MODE`.
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