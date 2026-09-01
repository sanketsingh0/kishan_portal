"""Tests for the Phase 1 data model layer.

All tests run against the isolated in-memory SQLite database created by the
`app` fixture in tests/conftest.py. They never touch a real database.
"""

from datetime import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Centre, Crop, Farmer, Staff, User, UserRole
from app.services.seed import seed_demo


# --- Database initialization ------------------------------------------------


def test_db_initialization_smoke(app):
    result = db.session.execute(text("SELECT 1"))
    assert result.scalar() == 1
    assert db.engine.dialect.name == "sqlite"  # confirms isolated test DB


def test_all_phase1_tables_exist(app):
    inspector = db.inspect(db.engine)
    tables = set(inspector.get_table_names())
    assert {"users", "farmers", "staff", "centres", "crops"} <= tables


# --- User model / roles -----------------------------------------------------


def test_user_roles_are_stored(app):
    admin = User(role=UserRole.ADMIN)
    staff = User(role=UserRole.STAFF)
    farmer = User(role=UserRole.FARMER)
    db.session.add_all([admin, staff, farmer])
    db.session.commit()

    roles = {u.role for u in User.query.all()}
    assert roles == {UserRole.ADMIN, UserRole.STAFF, UserRole.FARMER}


def test_user_defaults(app):
    user = User()
    db.session.add(user)
    db.session.commit()
    assert user.role == UserRole.FARMER
    assert user.is_active is True
    assert user.supabase_user_id is None
    assert user.created_at is not None
    assert user.updated_at is not None


def test_invalid_role_is_rejected_by_database(app):
    user = User(role="VISITOR")  # not in the CHECK constraint
    db.session.add(user)
    with pytest.raises(IntegrityError):
        db.session.commit()


# --- Farmer -> User ---------------------------------------------------------


def test_farmer_user_relationship(app):
    user = User(role=UserRole.FARMER, supabase_user_id="sb-farmer-0001")
    farmer = Farmer(user=user, name="Demo Farmer Ravi", phone="9876500001")
    db.session.add_all([user, farmer])
    db.session.commit()

    db.session.expire_all()
    stored_user = db.session.get(User, user.id)
    assert stored_user.farmer.name == "Demo Farmer Ravi"
    assert stored_user.farmer.user_id == user.id
    assert stored_user.farmer.created_at is not None


def test_one_farmer_profile_per_user(app):
    user = User(role=UserRole.FARMER)
    db.session.add(user)
    db.session.commit()

    db.session.add(Farmer(user_id=user.id, name="First"))
    db.session.commit()
    assert Farmer.query.count() == 1

    db.session.add(Farmer(user_id=user.id, name="Second"))
    with pytest.raises(IntegrityError):
        db.session.commit()


# --- Staff -> User / Centre -------------------------------------------------


def test_staff_user_relationship(app):
    user = User(role=UserRole.STAFF, supabase_user_id="sb-staff-0001")
    staff = Staff(user=user, name="Demo Staff Member", phone="9876500002")
    db.session.add_all([user, staff])
    db.session.commit()

    db.session.expire_all()
    stored_user = db.session.get(User, user.id)
    assert stored_user.staff.name == "Demo Staff Member"
    assert stored_user.staff.user_id == user.id


def test_staff_centre_relationship(app):
    centre = Centre(name="Demo Staff Centre", location="Demo Sector 9 (fictional)")
    user = User(role=UserRole.STAFF)
    staff = Staff(user=user, name="Demo Staff Member", centre=centre)
    db.session.add(centre)
    db.session.add_all([user, staff])
    db.session.commit()

    db.session.expire_all()
    stored_staff = db.session.get(Staff, staff.id)
    assert stored_staff.centre.name == "Demo Staff Centre"
    assert centre.staff[0].name == "Demo Staff Member"


def test_staff_centre_is_optional(app):
    staff = Staff(user=User(role=UserRole.STAFF), name="Unassigned Staff")
    db.session.add(staff)
    db.session.commit()
    assert staff.centre_id is None


# --- Centre model -----------------------------------------------------------


def test_centre_creation(app):
    centre = Centre(
        name="Demo Mandi - Block A",
        location="Demo Sector 1, Demo District (fictional)",
        opening_time=time(8, 0),
        closing_time=time(17, 0),
        daily_capacity=200,
        average_processing_minutes=15,
        is_active=True,
    )
    db.session.add(centre)
    db.session.commit()

    assert centre.id is not None
    assert centre.opening_time == time(8, 0)
    assert centre.closing_time == time(17, 0)
    assert centre.daily_capacity == 200
    assert centre.average_processing_minutes == 15
    assert centre.is_active is True
    assert centre.created_at is not None


# --- Crop model -------------------------------------------------------------


def test_crop_creation(app):
    crop = Crop(name="Wheat", category="Cereals")
    db.session.add(crop)
    db.session.commit()

    assert crop.id is not None
    assert crop.name == "Wheat"
    assert crop.category == "Cereals"
    assert crop.is_active is True  # default


# --- Unique constraints -----------------------------------------------------


def test_unique_centre_name(app):
    payload = {"name": "Dupe Mandi", "location": "Demo Sector 2 (fictional)"}
    db.session.add(Centre(**payload))
    db.session.commit()
    db.session.add(Centre(**payload))
    with pytest.raises(IntegrityError):
        db.session.commit()
def test_unique_crop_name(app):
    db.session.add(Crop(name="Soybean", category="Oilseeds"))
    db.session.commit()
    db.session.add(Crop(name="Soybean", category="Pulses"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_unique_supabase_user_id(app):
    db.session.add(User(role=UserRole.FARMER, supabase_user_id="sb-dup"))
    db.session.commit()
    db.session.add(User(role=UserRole.STAFF, supabase_user_id="sb-dup"))
    with pytest.raises(IntegrityError):
        db.session.commit()


# --- Seeder ----------------------------------------------------------------


def test_seed_demo_is_idempotent(app):
    first = seed_demo()
    second = seed_demo()

    assert first["centres"] > 0
    assert first["crops"] > 0
    assert second["centres"] == 0
    assert second["crops"] == 0
    assert Centre.query.count() == first["centres"]
    assert Crop.query.count() == first["crops"]