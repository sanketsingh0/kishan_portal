"""Quick SIH Demo Validation - Security & Isolation."""
import sys
from unittest.mock import MagicMock, patch
from app import create_app
from app.extensions import db
from app.models import User, UserRole, Booking, Farmer, Staff
from app.services.full_seed import seed_demo_full

def auth_header(t="t"): return {"Authorization": f"Bearer {t}"}

def mock_auth(user):
    mc = MagicMock()
    mc.auth = MagicMock()
    su = MagicMock()
    su.id = user.supabase_user_id or f"s-{user.id}"
    mc.auth.get_user.return_value = MagicMock(user=su)
    return patch("app.auth.service.get_supabase_client", return_value=mc), \
           patch("app.auth.decorators.get_local_user", return_value=user)

app = create_app("testing")
client = app.test_client()
with app.app_context():
    db.create_all()
    seed_demo_full()
    farmer = User.query.filter_by(role=UserRole.FARMER).first()
    staff = User.query.filter_by(role=UserRole.STAFF).first()
    admin = User.query.filter_by(role=UserRole.ADMIN).first()

results = []
def r(n, p, d=""):
    print(f"  [{'PASS' if p else 'FAIL'}] {n}" + (f" -- {d}" if d else ""))
    results.append(p)

print("=== SIH DEMO VALIDATION ===")

# Security: Unauthenticated
print("\n--- Unauthenticated ---")
r("Unauth -> farmer endpoint", client.get("/api/farmers/me").status_code == 401)
r("Unauth -> admin endpoint", client.get("/api/admin/analytics/overview").status_code == 401)
r("Unauth -> staff endpoint", client.get("/staff/dashboard").status_code == 401)

# Security: Farmer isolation
print("\n--- Farmer Isolation ---")
gc, gl = mock_auth(farmer)
with gc, gl:
    r("Farmer -> profile", client.get("/api/farmers/me", headers=auth_header()).status_code == 200)
    r("Farmer -> bookings", client.get("/api/bookings/my", headers=auth_header()).status_code == 200)
    r("Farmer -> admin BLOCKED", client.get("/api/admin/analytics/overview", headers=auth_header()).status_code == 403)
    r("Farmer -> staff BLOCKED", client.get("/staff/dashboard", headers=auth_header()).status_code == 403)
    r("Farmer -> centre queue BLOCKED", client.get("/api/queue/centre/1", headers=auth_header()).status_code == 403)

# Security: Staff isolation
print("\n--- Staff Isolation ---")
gc, gl = mock_auth(staff)
with gc, gl:
    r("Staff -> dashboard", client.get("/staff/dashboard", headers=auth_header()).status_code == 200)
    r("Staff -> admin BLOCKED", client.get("/api/admin/analytics/overview", headers=auth_header()).status_code == 403)
    r("Staff -> audit logs BLOCKED", client.get("/api/admin/audit-logs", headers=auth_header()).status_code == 403)

# Data: Seed integrity
print("\n--- Seed Data ---")
with app.app_context():
    r("5 bookings seeded", Booking.query.count() == 5)
    r("5 farmers seeded", Farmer.query.count() == 5)
    r("2 staff seeded", Staff.query.count() == 2)

# UI: Pages load
print("\n--- UI Pages ---")
for url in ["/", "/login", "/farmer/dashboard", "/admin/dashboard"]:
    r(f"Page {url}", client.get(url).status_code == 200)

# Summary
passed = sum(results)
total = len(results)
print(f"\n=== RESULTS: {passed}/{total} passed ===")
sys.exit(0 if passed == total else 1)
