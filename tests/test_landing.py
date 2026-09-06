"""Tests for the KisanProcure landing page and public API."""
import os
from datetime import date, time, timedelta
from app.extensions import db
from app.models import Centre, Crop, Slot, SlotStatus

LANDING_JS = os.path.join(os.path.dirname(__file__), "..", "app", "static", "js", "landing.js")


def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "KisanProcure" in body and "Government of India" in body


def test_landing_page_skip_link(client):
    resp = client.get("/")
    assert 'skip-link' in resp.data.decode("utf-8")


def test_landing_page_auth_tabs(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "FARMER" in body and "STAFF" in body and "ADMIN" in body


def test_landing_page_uses_existing_login(client):
    resp = client.get("/")
    assert "landing.js" in resp.data.decode("utf-8")
    with open(LANDING_JS, "r", encoding="utf-8") as f:
        assert "/api/auth/login" in f.read()


def test_landing_page_links(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert 'href="/register"' in body and 'href="/login"' in body
    assert "auth.js" in body and "landing.js" in body


def test_landing_page_sections(client):
    resp = client.get("/")
    body = resp.data.decode("utf-8")
    assert "Procurement Centers" in body
    assert "Live Procurement Information" in body
    assert "Notice Board" in body and "Coming Soon" in body


def test_landing_page_disclaimer(client):
    resp = client.get("/")
    assert "not an official Government of India service" in resp.data.decode("utf-8")


def test_landing_page_notice_future(client):
    resp = client.get("/")
    assert "Upcoming Feature" in resp.data.decode("utf-8")


def test_landing_page_redirects(client):
    with open(LANDING_JS, "r", encoding="utf-8") as f:
        js = f.read()
    assert "/farmer/dashboard" in js
    assert "/staff/dashboard" in js
    assert "/admin/dashboard" in js


def test_public_centres_no_auth(client):
    c = Centre(name="Test Mandi", location="Loc", daily_capacity=100, is_active=True)
    db.session.add(c)
    db.session.commit()
    resp = client.get("/api/public/centres")
    assert resp.status_code == 200
    assert len(resp.get_json()["centres"]) >= 1


def test_public_centres_excludes_inactive(client):
    a = Centre(name="Active", location="A", daily_capacity=50, is_active=True)
    i = Centre(name="Inactive", location="B", daily_capacity=50, is_active=False)
    db.session.add_all([a, i])
    db.session.commit()
    resp = client.get("/api/public/centres")
    names = [c["name"] for c in resp.get_json()["centres"]]
    assert "Active" in names and "Inactive" not in names


def test_public_centres_empty(client):
    resp = client.get("/api/public/centres")
    assert resp.status_code == 200 and resp.get_json()["centres"] == []


def test_public_slots_no_auth(client):
    centre = Centre(name="Slot Mandi", location="Loc", daily_capacity=100, is_active=True)
    crop = Crop(name="Wheat", category="Cereal", is_active=True)
    db.session.add_all([centre, crop])
    db.session.flush()
    slot = Slot(centre_id=centre.id, crop_id=crop.id,
                slot_date=date.today()+timedelta(days=1),
                start_time=time(9,0), end_time=time(12,0),
                capacity=20, status=SlotStatus.OPEN)
    db.session.add(slot)
    db.session.commit()
    resp = client.get("/api/public/slots")
    assert resp.status_code == 200
    data = resp.get_json()["slots"]
    assert len(data) >= 1 and data[0]["centre_name"] == "Slot Mandi"


def test_public_slots_excludes_non_open(client):
    centre = Centre(name="Status Mandi", location="Loc", daily_capacity=100, is_active=True)
    crop = Crop(name="Rice", category="Cereal", is_active=True)
    db.session.add_all([centre, crop])
    db.session.flush()
    s1 = Slot(centre_id=centre.id, crop_id=crop.id,
              slot_date=date.today()+timedelta(days=1),
              start_time=time(9,0), end_time=time(10,0),
              capacity=10, status=SlotStatus.OPEN)
    s2 = Slot(centre_id=centre.id, crop_id=crop.id,
              slot_date=date.today()+timedelta(days=1),
              start_time=time(11,0), end_time=time(12,0),
              capacity=10, status=SlotStatus.CLOSED)
    db.session.add_all([s1, s2])
    db.session.commit()
    resp = client.get("/api/public/slots")
    statuses = [s["status"] for s in resp.get_json()["slots"]]
    assert "OPEN" in statuses and "CLOSED" not in statuses


def test_public_slots_excludes_past(client):
    centre = Centre(name="Past Mandi", location="Loc", daily_capacity=100, is_active=True)
    crop = Crop(name="Maize", category="Cereal", is_active=True)
    db.session.add_all([centre, crop])
    db.session.flush()
    past = Slot(centre_id=centre.id, crop_id=crop.id,
                slot_date=date.today()-timedelta(days=1),
                start_time=time(9,0), end_time=time(10,0),
                capacity=10, status=SlotStatus.OPEN)
    db.session.add(past)
    db.session.commit()
    resp = client.get("/api/public/slots")
    assert resp.get_json()["slots"] == []


def test_public_slots_empty(client):
    resp = client.get("/api/public/slots")
    assert resp.status_code == 200 and resp.get_json()["slots"] == []


def test_public_slots_filter_by_centre(client):
    c1 = Centre(name="C1", location="A", daily_capacity=50, is_active=True)
    c2 = Centre(name="C2", location="B", daily_capacity=50, is_active=True)
    crop = Crop(name="Barley", category="Cereal", is_active=True)
    db.session.add_all([c1, c2, crop])
    db.session.flush()
    s1 = Slot(centre_id=c1.id, crop_id=crop.id, slot_date=date.today()+timedelta(days=1),
              start_time=time(9,0), end_time=time(10,0), capacity=10, status=SlotStatus.OPEN)
    s2 = Slot(centre_id=c2.id, crop_id=crop.id, slot_date=date.today()+timedelta(days=1),
              start_time=time(9,0), end_time=time(10,0), capacity=10, status=SlotStatus.OPEN)
    db.session.add_all([s1, s2])
    db.session.commit()
    resp = client.get(f"/api/public/slots?centre_id={c1.id}")
    assert len(resp.get_json()["slots"]) == 1
