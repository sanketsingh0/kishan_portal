"""Tests for Farmer Location-Based Centre Eligibility (tehsil OR district).

Rule enforced in ``app/services/booking_service.py``:

    normalized(farmer.tehsil)   == normalized(centre.tehsil)
    OR
    normalized(farmer.district) == normalized(centre.district)

Normalization = trim + case-insensitive, exact (never partial/fuzzy) equality.
If farmer and centre have no usable matching location data (including both
sides unconfigured) the booking is REJECTED — there is no legacy
both-sides-unconfigured allowance.
The restriction applies ONLY to farmer slot booking; staff/admin flows
(carry-forward, centre management, queue, QR/procurement) are untouched.
"""

from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models import (
    Booking,
    BookingStatus,
    BookingCarryForward,
    Centre,
    Crop,
    Farmer,
    Procurement,
    ProcurementStatus,
    Slot,
    SlotStatus,
    Staff,
    User,
    UserRole,
)
from app.services.booking_service import (
    LOCATION_MISMATCH_MESSAGE,
    BookingValidationError,
    check_location_eligibility,
    create_booking,
    is_location_eligible,
)

FUTURE = date.today() + timedelta(days=3)
PAST = date.today() - timedelta(days=1)
_seq = {"n": 0}


def _uniq(prefix: str) -> str:
    """Return a per-run unique name (Centre.name / Crop.name are UNIQUE)."""
    _seq["n"] += 1
    return f"{prefix}-{_seq['n']}"


def make_mock_user(user_id="x"):
    u = MagicMock()
    u.id = user_id
    return u


def auth_header(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


def call_api(client, supa_id, method, url, payload=None):
    """Call the API as a mocked, authenticated Supabase user."""
    su = make_mock_user(user_id=supa_id)
    with patch("app.auth.service.get_supabase_client") as mock_gc:
        mock_client = MagicMock()
        mock_gc.return_value = mock_client
        mock_client.auth.get_user.return_value.user = su
        if method == "GET":
            return client.get(url, headers=auth_header())
        if method == "PUT":
            return client.put(url, json=payload or {}, headers=auth_header())
        return client.post(url, json=payload or {}, headers=auth_header())


def ns(district=None, tehsil=None):
    """Lightweight stand-in for a Farmer/Centre (only location attrs matter)."""
    return SimpleNamespace(district=district, tehsil=tehsil)


def add_user(supa_id, role=UserRole.FARMER):
    u = User(supabase_user_id=supa_id, role=role, is_active=True)
    db.session.add(u)
    db.session.flush()
    return u


def add_farmer(supa_id, district=None, tehsil=None):
    u = add_user(supa_id)
    f = Farmer(
        user_id=u.id,
        name=_uniq("Loc Farmer"),
        phone=f"9{_seq['n']:09d}",
        district=district,
        tehsil=tehsil,
    )
    db.session.add(f)
    db.session.flush()
    return u, f


def add_centre(district=None, tehsil=None, is_active=True, day_offset=0):
    """Create a centre; ``day_offset`` staggers slot dates used by the fixture.

    Slots belonging to one centre must fall on different dates because the
    service enforces the centre's ``daily_capacity`` per date, and slot
    creation computes each centre's daily window from the first slot it sees.
    """
    c = Centre(
        name=_uniq("Loc Centre"),
        location="Loc Yard",
        district=district,
        tehsil=tehsil,
        opening_time=time(0, 0),
        closing_time=time(23, 59),
        daily_capacity=100,
        is_active=is_active,
    )
    db.session.add(c)
    db.session.flush()
    c._loc_day_offset = day_offset
    return c


def add_crop():
    cr = Crop(name=_uniq("Loc Crop"), category="Cereal", is_active=True)
    db.session.add(cr)
    db.session.flush()
    return cr


def add_slot(centre, crop, capacity=5, hour=9, slot_date=FUTURE,
             status=SlotStatus.OPEN):
    s = Slot(
        centre_id=centre.id,
        crop_id=crop.id,
        slot_date=slot_date,
        start_time=time(hour, 0),
        end_time=time(hour + 1, 0),
        capacity=capacity,
        status=status,
    )
    db.session.add(s)
    db.session.flush()
    return s


@pytest.fixture
def loc(app):
    """Centre (Mirzapur / Mirzapur Sadar) + crop + OPEN future slots.

    ``slot_id``        : capacity 5 on day+3 at 09:00
    ``slot_b_id``      : capacity 1 on day+4 at 12:00 (capacity tests)
    ``slot_closed_id`` : CLOSED status
    ``slot_past_id``   : past date
    """
    with app.app_context():
        crop = add_crop()
        centre = add_centre(district="Mirzapur", tehsil="Mirzapur Sadar")
        slot = add_slot(centre, crop, hour=9)
        slot_b = add_slot(centre, crop, capacity=1, hour=12,
                          slot_date=date.today() + timedelta(days=4))
        slot_closed = add_slot(centre, crop, capacity=5, hour=14,
                               slot_date=date.today() + timedelta(days=4),
                               status=SlotStatus.CLOSED)
        slot_past = add_slot(centre, crop, capacity=5, hour=15, slot_date=PAST)
        db.session.commit()
        yield {
            "crop_id": crop.id,
            "centre_id": centre.id,
            "slot_id": slot.id,
            "slot_b_id": slot_b.id,
            "slot_closed_id": slot_closed.id,
            "slot_past_id": slot_past.id,
        }


class TestLocationEligibilityRule:
    """Unit tests for ``is_location_eligible`` (pure rule, no HTTP/db)."""

    # ---- Allowed cases -------------------------------------------------
    def test_tehsil_match_only_is_allowed(self):
        assert is_location_eligible(
            ns(district="Varanasi", tehsil="Mirzapur Sadar"),
            ns(district="Varanasi", tehsil="Mirzapur Sadar"),
        ) is True

    def test_farmer_tehsil_matches_centre_tehsil_only(self):
        """Farmer tehsil match wins even when districts differ (spec example)."""
        assert is_location_eligible(
            ns(district="Varanasi", tehsil="Mirzapur Sadar"),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is True

    def test_farmer_district_matches_centre_district_only(self):
        """Farmer district match wins even when tehsils differ (spec example)."""
        assert is_location_eligible(
            ns(district="Mirzapur", tehsil="Varanasi Sadar"),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is True

    def test_both_levels_match_is_allowed(self):
        assert is_location_eligible(
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is True

    # ---- Rejected cases ------------------------------------------------
    def test_neither_level_matches_is_rejected(self):
        assert is_location_eligible(
            ns(district="Varanasi", tehsil="Varanasi Sadar"),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is False

    def test_farmer_tehsil_missing_district_matches_is_allowed(self):
        assert is_location_eligible(
            ns(district="Mirzapur", tehsil=None),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is True

    def test_farmer_district_missing_tehsil_matches_is_allowed(self):
        assert is_location_eligible(
            ns(district=None, tehsil="Mirzapur Sadar"),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is True

    def test_both_farmer_values_missing_is_rejected(self):
        """A farmer with no jurisdiction data cannot match a configured centre."""
        assert is_location_eligible(
            ns(district=None, tehsil=None),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is False

    def test_centre_tehsil_missing_district_matches_is_allowed(self):
        assert is_location_eligible(
            ns(district="Mirzapur", tehsil="Varanasi Sadar"),
            ns(district="Mirzapur", tehsil=None),
        ) is True

    def test_centre_district_missing_tehsil_matches_is_allowed(self):
        assert is_location_eligible(
            ns(district="Varanasi", tehsil="Mirzapur Sadar"),
            ns(district=None, tehsil="Mirzapur Sadar"),
        ) is True

    def test_farmer_location_present_but_centre_unconfigured_is_rejected(self):
        """No centre jurisdiction => nothing to match => rejected (strict)."""
        assert is_location_eligible(
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
            ns(district=None, tehsil=None),
        ) is False

    def test_both_sides_unconfigured_is_rejected(self):
        """No usable matching location data on either side => rejected.

        Replaces the legacy both-sides-unconfigured allowance: booking is
        allowed ONLY when normalized tehsil or district matches.
        """
        assert is_location_eligible(
            ns(district=None, tehsil=None),
            ns(district=None, tehsil=None),
        ) is False

    def test_both_sides_blank_strings_is_rejected(self):
        """Whitespace-only values normalize to missing => still rejected."""
        assert is_location_eligible(
            ns(district="   ", tehsil=""),
            ns(district=None, tehsil="\\t\\n"),
        ) is False

    # ---- Normalization -------------------------------------------------
    def test_case_differences_still_match(self):
        assert is_location_eligible(
            ns(district="  MIRZAPUR ", tehsil="mirzapur sadar"),
            ns(district="Mirzapur", tehsil="MIRZAPUR SADAR"),
        ) is True

    def test_leading_trailing_whitespace_still_matches(self):
        assert is_location_eligible(
            ns(district="  Mirzapur  ", tehsil="\tMirzapur Sadar\n"),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is True

    def test_partial_strings_do_not_match(self):
        """"Varanasi" must not match "Varanasi Sadar" at the tehsil level."""
        assert is_location_eligible(
            ns(district="Varanasi", tehsil="Varanasi"),
            ns(district="Mirzapur", tehsil="Varanasi Sadar"),
        ) is False
        assert is_location_eligible(
            ns(district="Mirzapur Purba", tehsil="X"),
            ns(district="Mirzapur", tehsil="Y"),
        ) is False

    def test_empty_strings_are_treated_as_missing(self):
        assert is_location_eligible(
            ns(district="   ", tehsil=""),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        ) is False

    def test_check_location_eligibility_raises_validation_error(self):
        with pytest.raises(BookingValidationError) as exc_info:
            check_location_eligibility(
                ns(district="Varanasi", tehsil="Varanasi Sadar"),
                ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
            )
        assert exc_info.value.code == "VALIDATION_ERROR"
        assert LOCATION_MISMATCH_MESSAGE in exc_info.value.errors

    def test_check_location_eligibility_passes_on_match(self):
        check_location_eligibility(
            ns(district="Mirzapur", tehsil="Varanasi Sadar"),
            ns(district="Mirzapur", tehsil="Mirzapur Sadar"),
        )


def _make_farmer_in_db(app, district, tehsil, supa_id):
    """Create a farmer with the given jurisdiction; returns (user_id, farmer_id)."""
    with app.app_context():
        u, f = add_farmer(supa_id, district=district, tehsil=tehsil)
        db.session.commit()
        return u.id, f.id


def _centre_with_staff(app, supa_id, district="Mirzapur",
                       tehsil="Mirzapur Sadar"):
    """Create a centre plus a STAFF user assigned to it; returns centre id."""
    with app.app_context():
        centre = add_centre(district=district, tehsil=tehsil)
        u = add_user(supa_id, role=UserRole.STAFF)
        db.session.add(Staff(user_id=u.id, name=_uniq("Loc Staff"),
                             centre_id=centre.id))
        db.session.commit()
        return centre.id


def _admin(app, supa_id):
    with app.app_context():
        u = add_user(supa_id, role=UserRole.ADMIN)
        db.session.commit()
        return u.id


def _slot_via_api(client, app, loc, supa_id, day_offset=0, capacity=5, hour=9,
                  crop_id=None, district="Mirzapur", tehsil="Mirzapur Sadar"):
    """Create centre (optional) + slot through the STAFF slot API."""
    centre_id = _centre_with_staff(app, supa_id, district=district, tehsil=tehsil)
    slot_date = str(date.today() + timedelta(days=2 + day_offset))
    resp = call_api(client, supa_id, "POST", "/api/slots", {
        "crop_id": crop_id or loc["crop_id"],
        "slot_date": slot_date,
        "start_time": f"{hour:02d}:00",
        "end_time": f"{hour + 1:02d}:00",
        "capacity": capacity,
    })
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()["slot"]
    return centre_id, body["id"], body


class TestBookingApiLocationEnforcement:
    """POST /api/bookings must reject ineligible farmers (server-side truth)."""

    def test_tehsil_match_allows_booking(self, client, app, loc):
        _, farmer_id = _make_farmer_in_db(app, "Varanasi", "Mirzapur Sadar",
                                          "loc-t-farmer-tehsil")
        resp = call_api(client, "loc-t-farmer-tehsil", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"]})
        assert resp.status_code == 201, resp.get_json()
        data = resp.get_json()
        assert data["message"] == "Booking created successfully"
        assert data["booking"]["status"] == "CONFIRMED"
        assert data["booking"]["token_number"].startswith("K-")
        with app.app_context():
            assert Booking.query.filter_by(farmer_id=farmer_id).count() == 1

    def test_district_match_allows_booking(self, client, app, loc):
        _make_farmer_in_db(app, "Mirzapur", "Varanasi Sadar", "loc-t-farmer-district")
        resp = call_api(client, "loc-t-farmer-district", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"]})
        assert resp.status_code == 201, resp.get_json()

    def test_both_levels_match_allow_booking(self, client, app, loc):
        _make_farmer_in_db(app, "Mirzapur", "Mirzapur Sadar", "loc-t-farmer-both")
        resp = call_api(client, "loc-t-farmer-both", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"]})
        assert resp.status_code == 201, resp.get_json()

    def test_normalized_case_and_whitespace_allow_booking(self, client, app, loc):
        _make_farmer_in_db(app, "  MIRZAPUR  ", " mirzapur sadar ",
                           "loc-t-farmer-normalized")
        resp = call_api(client, "loc-t-farmer-normalized", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"]})
        assert resp.status_code == 201, resp.get_json()

    def test_centre_tehsil_missing_district_match_allows_booking(self, client, app, loc):
        with app.app_context():
            centre = add_centre(district="Mirzapur", tehsil=None)
            slot = add_slot(centre, db.session.get(Crop, loc["crop_id"]), hour=11)
            db.session.commit()
            slot_id = slot.id
        _make_farmer_in_db(app, "Mirzapur", "Varanasi Sadar", "loc-t-farmer-no-tehsil")
        resp = call_api(client, "loc-t-farmer-no-tehsil", "POST", "/api/bookings",
                        {"slot_id": slot_id})
        assert resp.status_code == 201, resp.get_json()

    def test_centre_district_missing_tehsil_match_allows_booking(self, client, app, loc):
        with app.app_context():
            centre = add_centre(district=None, tehsil="Mirzapur Sadar")
            slot = add_slot(centre, db.session.get(Crop, loc["crop_id"]), hour=11)
            db.session.commit()
            slot_id = slot.id
        _make_farmer_in_db(app, "Varanasi", "Mirzapur Sadar", "loc-t-farmer-no-district")
        resp = call_api(client, "loc-t-farmer-no-district", "POST", "/api/bookings",
                        {"slot_id": slot_id})
        assert resp.status_code == 201, resp.get_json()

    # ---- Rejected ------------------------------------------------------
    def test_neither_level_matches_rejects_booking(self, client, app, loc):
        _, farmer_id = _make_farmer_in_db(app, "Varanasi", "Varanasi Sadar",
                                          "loc-t-farmer-mismatch")
        resp = call_api(client, "loc-t-farmer-mismatch", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"]})
        assert resp.status_code == 400, resp.get_json()
        body = resp.get_json()
        assert body["error"] == "Validation failed"
        assert LOCATION_MISMATCH_MESSAGE in body["messages"]
        with app.app_context():
            assert Booking.query.filter_by(farmer_id=farmer_id).count() == 0

    def test_farmer_without_any_location_rejected(self, client, app, loc):
        _, farmer_id = _make_farmer_in_db(app, None, None, "loc-t-farmer-blank")
        resp = call_api(client, "loc-t-farmer-blank", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"]})
        assert resp.status_code == 400, resp.get_json()
        assert LOCATION_MISMATCH_MESSAGE in resp.get_json()["messages"]
        with app.app_context():
            assert Booking.query.filter_by(farmer_id=farmer_id).count() == 0

    def test_both_sides_unconfigured_rejected_by_api(self, client, app, loc):
        """Farmer AND centre both without location data => booking rejected."""
        with app.app_context():
            centre = add_centre(district=None, tehsil=None)
            slot = add_slot(centre, db.session.get(Crop, loc["crop_id"]), hour=11)
            db.session.commit()
            slot_id = slot.id
        _, farmer_id = _make_farmer_in_db(app, None, None, "loc-t-farmer-legacy")
        resp = call_api(client, "loc-t-farmer-legacy", "POST", "/api/bookings",
                        {"slot_id": slot_id})
        assert resp.status_code == 400, resp.get_json()
        body = resp.get_json()
        assert body["error"] == "Validation failed"
        assert LOCATION_MISMATCH_MESSAGE in body["messages"]
        with app.app_context():
            assert Booking.query.filter_by(farmer_id=farmer_id).count() == 0

    def test_partial_location_match_rejected_by_api(self, client, app, loc):
        _make_farmer_in_db(app, "Varanasi", "Mirzapur", "loc-t-farmer-partial")
        resp = call_api(client, "loc-t-farmer-partial", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"]})
        assert resp.status_code == 400, resp.get_json()

    def test_unconfigured_centre_rejects_configured_farmer(self, client, app, loc):
        with app.app_context():
            centre = add_centre(district=None, tehsil=None)
            slot = add_slot(centre, db.session.get(Crop, loc["crop_id"]), hour=11)
            db.session.commit()
            slot_id = slot.id
        _make_farmer_in_db(app, "Mirzapur", "Mirzapur Sadar", "loc-t-farmer-unconf")
        resp = call_api(client, "loc-t-farmer-unconf", "POST", "/api/bookings",
                        {"slot_id": slot_id})
        assert resp.status_code == 400, resp.get_json()

    def test_service_layer_rejects_independent_of_route(self, client, app, loc):
        """create_booking() itself rejects, so a directly-called service cannot bypass."""
        with app.app_context():
            u, f = add_farmer("loc-t-farmer-service", district="Varanasi",
                              tehsil="Varanasi Sadar")
            db.session.commit()
            farmer_user_id, farmer_id = f.user_id, f.id
            with pytest.raises(BookingValidationError) as exc_info:
                create_booking(user_id=farmer_user_id, slot_id=loc["slot_id"])
            assert LOCATION_MISMATCH_MESSAGE in exc_info.value.errors
            db.session.rollback()
            assert Booking.query.filter_by(farmer_id=farmer_id).count() == 0


class TestBookingLocationBypassAttempts:
    """Client-supplied identity/location must not influence eligibility."""

    def test_client_supplied_farmer_id_cannot_bypass(self, client, app, loc):
        with app.app_context():
            _, eligible = add_farmer("loc-b-eligible", district="Mirzapur",
                                     tehsil="Mirzapur Sadar")
            _, ineligible = add_farmer("loc-b-ineligible", district="Varanasi",
                                       tehsil="Varanasi Sadar")
            db.session.commit()
            eligible_id, ineligible_id = eligible.id, ineligible.id

        resp = call_api(client, "loc-b-ineligible", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"], "farmer_id": eligible_id,
                         "user_id": eligible_id})
        assert resp.status_code == 400, resp.get_json()
        assert LOCATION_MISMATCH_MESSAGE in resp.get_json()["messages"]
        with app.app_context():
            assert Booking.query.count() == 0
            assert Booking.query.filter_by(farmer_id=eligible_id).count() == 0
            assert Booking.query.filter_by(farmer_id=ineligible_id).count() == 0

    def test_client_supplied_location_cannot_bypass(self, client, app, loc):
        with app.app_context():
            _, farmer = add_farmer("loc-b-spoof-loc", district="Varanasi",
                                   tehsil="Varanasi Sadar")
            db.session.commit()
            farmer_id = farmer.id

        resp = call_api(client, "loc-b-spoof-loc", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"], "district": "Mirzapur",
                         "tehsil": "Mirzapur Sadar"})
        assert resp.status_code == 400, resp.get_json()
        with app.app_context():
            assert Booking.query.filter_by(farmer_id=farmer_id).count() == 0

    def test_booking_created_for_authenticated_farmer_only(self, client, app, loc):
        with app.app_context():
            _, eligible = add_farmer("loc-b-owner", district="Mirzapur",
                                     tehsil="Varanasi Sadar")
            _, other = add_farmer("loc-b-other", district="Varanasi",
                                  tehsil="Varanasi Sadar")
            db.session.commit()
            eligible_id, other_id = eligible.id, other.id

        resp = call_api(client, "loc-b-owner", "POST", "/api/bookings",
                        {"slot_id": loc["slot_id"], "farmer_id": other_id})
        assert resp.status_code == 201, resp.get_json()
        with app.app_context():
            rows = Booking.query.all()
            assert len(rows) == 1
            assert rows[0].farmer_id == eligible_id
            assert Booking.query.filter_by(farmer_id=other_id).count() == 0


class TestValidationOrderAndRegression:
    """Existing validations must still run; unrelated flows must be untouched."""

    def _farmer(self, app, district, tehsil, supa_id):
        with app.app_context():
            u, f = add_farmer(supa_id, district=district, tehsil=tehsil)
            db.session.commit()
            return f.id

    def test_location_check_does_not_precede_slot_state_validation(self, client, app, loc):
        """Existing slot-state checks keep precedence over the location rule."""
        self._farmer(app, "Varanasi", "Varanasi Sadar", "loc-r-order")

        resp_closed = call_api(client, "loc-r-order", "POST", "/api/bookings",
                               {"slot_id": loc["slot_closed_id"]})
        assert resp_closed.status_code == 400, resp_closed.get_json()
        assert resp_closed.get_json()["messages"] == ["Slot is not open for booking."]

        resp_past = call_api(client, "loc-r-order", "POST", "/api/bookings",
                             {"slot_id": loc["slot_past_id"]})
        assert resp_past.status_code == 400, resp_past.get_json()
        assert resp_past.get_json()["messages"] == ["Cannot book slots in the past."]

        # Ineligible farmer still rejected for an otherwise valid future slot.
        resp_valid = call_api(client, "loc-r-order", "POST", "/api/bookings",
                              {"slot_id": loc["slot_id"]})
        assert resp_valid.status_code == 400, resp_valid.get_json()
        assert LOCATION_MISMATCH_MESSAGE in resp_valid.get_json()["messages"]

    def test_duplicate_booking_validation_still_enforced(self, client, app, loc):
        farmer_id = self._farmer(app, "Mirzapur", "Mirzapur Sadar", "loc-r-dup")
        first = call_api(client, "loc-r-dup", "POST", "/api/bookings",
                         {"slot_id": loc["slot_id"]})
        assert first.status_code == 201, first.get_json()

        second = call_api(client, "loc-r-dup", "POST", "/api/bookings",
                          {"slot_id": loc["slot_id"]})
        assert second.status_code == 409, second.get_json()
        assert second.get_json()["code"] == "DUPLICATE_BOOKING"
        with app.app_context():
            assert Booking.query.filter_by(farmer_id=farmer_id).count() == 1

    def test_capacity_validation_still_enforced(self, client, app, loc):
        with app.app_context():
            crop = db.session.get(Crop, loc["crop_id"])
            centre = db.session.get(Centre, loc["centre_id"])
            small = add_slot(centre, crop, capacity=1, hour=16)
            db.session.commit()
            small_id = small.id
        self._farmer(app, "Mirzapur", "Mirzapur Sadar", "loc-r-cap-1")
        self._farmer(app, "Mirzapur", "Mirzapur Sadar", "loc-r-cap-2")

        assert call_api(client, "loc-r-cap-1", "POST", "/api/bookings",
                        {"slot_id": small_id}).status_code == 201
        full = call_api(client, "loc-r-cap-2", "POST", "/api/bookings",
                        {"slot_id": small_id})
        assert full.status_code == 409, full.get_json()
        assert full.get_json()["code"] == "CAPACITY_EXCEEDED"

    def test_profile_change_keeps_existing_booking_but_blocks_new_one(self, client, app, loc):
        farmer_id = self._farmer(app, "Mirzapur", "Mirzapur Sadar", "loc-r-profile")
        created = call_api(client, "loc-r-profile", "POST", "/api/bookings",
                           {"slot_id": loc["slot_id"]})
        assert created.status_code == 201, created.get_json()

        edited = call_api(client, "loc-r-profile", "PUT", "/api/farmers/me",
                          {"district": "Varanasi", "tehsil": "Varanasi Sadar"})
        assert edited.status_code == 200, edited.get_json()

        with app.app_context():
            rows = Booking.query.filter_by(farmer_id=farmer_id).all()
            assert len(rows) == 1
            assert rows[0].status == BookingStatus.CONFIRMED
            assert rows[0].token_number

        # A new booking at the (now ineligible) centre is rejected.
        with app.app_context():
            crop = db.session.get(Crop, loc["crop_id"])
            centre = db.session.get(Centre, loc["centre_id"])
            other = add_slot(centre, crop, hour=13)
            db.session.commit()
            other_id = other.id
        blocked = call_api(client, "loc-r-profile", "POST", "/api/bookings",
                           {"slot_id": other_id})
        assert blocked.status_code == 400, blocked.get_json()
        assert LOCATION_MISMATCH_MESSAGE in blocked.get_json()["messages"]


class TestStaffAdminAndQueuePassUnaffected:
    """STAFF/ADMIN, carry-forward and Smart Queue Pass flows stay unrestricted."""

    def test_staff_carry_forward_unaffected_by_farmer_location(self, client, app, loc):
        centre_id = _centre_with_staff(app, "loc-r-staff-cf")
        with app.app_context():
            crop = db.session.get(Crop, loc["crop_id"])
            centre = db.session.get(Centre, centre_id)
            src = date.today() + timedelta(days=1)
            tgt = src + timedelta(days=1)
            s_src = add_slot(centre, crop, capacity=5, hour=9, slot_date=src)
            add_slot(centre, crop, capacity=5, hour=9, slot_date=tgt)
            _, farmer = add_farmer("loc-r-farmer-cf", district="Varanasi",
                                   tehsil="Varanasi Sadar")
            booking = Booking(farmer_id=farmer.id, slot_id=s_src.id,
                              status=BookingStatus.CONFIRMED, token_number="K-9101")
            db.session.add(booking)
            db.session.commit()
            booking_id = booking.id

        resp = call_api(client, "loc-r-staff-cf", "POST", "/api/staff/carry-forward",
                        {"booking_ids": [booking_id], "target_date": str(tgt),
                         "reason": "Centre closed"})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["successful_count"] == 1
        with app.app_context():
            assert db.session.get(Booking, booking_id).status == BookingStatus.CARRIED_FORWARD

    def test_smart_queue_pass_unaffected_by_farmer_location(self, client, app, loc):
        with app.app_context():
            crop = db.session.get(Crop, loc["crop_id"])
            centre = add_centre(district="Mirzapur", tehsil="Mirzapur Sadar")
            slot = add_slot(centre, crop, capacity=5, hour=10)
            _, farmer = add_farmer("loc-r-farmer-pass", district="Varanasi",
                                   tehsil="Varanasi Sadar")
            booking = Booking(farmer_id=farmer.id, slot_id=slot.id,
                              status=BookingStatus.CONFIRMED, token_number="K-9102")
            db.session.add(booking)
            db.session.commit()
            booking_id = booking.id

        resp = call_api(client, "loc-r-farmer-pass", "GET",
                        f"/api/queue-pass/my/{booking_id}")
        assert resp.status_code == 200, resp.get_json()
        pass_payload = resp.get_json()["smart_queue_pass"]
        assert pass_payload["booking"]["id"] == booking_id
        assert pass_payload["entry_verified"] is False

    def test_admin_centre_management_not_restricted(self, client, app):
        with app.app_context():
            add_user("loc-r-admin-centre", role=UserRole.ADMIN)
            db.session.commit()
        resp = call_api(client, "loc-r-admin-centre", "POST", "/api/centres",
                        {"name": _uniq("Loc Admin Centre"), "location": "Yard 1",
                         "opening_time": "08:00", "closing_time": "16:00",
                         "daily_capacity": 50, "average_processing_minutes": 10,
                         "district": "Mirzapur", "tehsil": "Mirzapur Sadar"})
        assert resp.status_code == 201, resp.get_json()
        centre = resp.get_json()["centre"]
        assert centre["district"] == "Mirzapur"
        assert centre["tehsil"] == "Mirzapur Sadar"

    def test_staff_slot_creation_not_restricted(self, client, app, loc):
        """STAFF slot management at their own centre ignores farmer jurisdiction."""
        _centre_with_staff(app, "loc-r-staff-slot")
        start = str(date.today() + timedelta(days=6))
        resp = call_api(client, "loc-r-staff-slot", "POST", "/api/slots",
                        {"crop_id": loc["crop_id"],
                         "slot_date": start, "start_time": "09:00",
                         "end_time": "10:00", "capacity": 5})
        assert resp.status_code == 201, resp.get_json()

    def test_slots_api_eligibility_flag_is_farmer_only(self, client, app, loc):
        with app.app_context():
            u_staff = add_user("loc-r-staff-list", role=UserRole.STAFF)
            centre = db.session.get(Centre, loc["centre_id"])
            db.session.add(Staff(user_id=u_staff.id, name="Loc List Staff",
                                 centre_id=centre.id))
            db.session.flush()
            add_farmer("loc-r-farmer-list", district="Varanasi",
                       tehsil="Varanasi Sadar")
            db.session.commit()

        farmer_resp = call_api(client, "loc-r-farmer-list", "GET", "/api/slots")
        assert farmer_resp.status_code == 200, farmer_resp.get_json()
        rows = [s for s in farmer_resp.get_json()["slots"] if s["id"] == loc["slot_id"]]
        assert rows, "loc slot missing from farmer slot catalogue"
        assert rows[0]["location_eligible"] is False
        assert rows[0]["centre_district"] == "Mirzapur"
        assert rows[0]["centre_tehsil"] == "Mirzapur Sadar"

        staff_resp = call_api(client, "loc-r-staff-list", "GET",
                              f"/api/slots?centre_id={loc['centre_id']}")
        assert staff_resp.status_code == 200, staff_resp.get_json()
        assert all("location_eligible" not in s
                   for s in staff_resp.get_json()["slots"])

    def test_null_centre_location_fields_do_not_break_slot_apis(self, client, app, loc):
        """J: legacy centres with NULL district/tehsil must not crash /api/slots."""
        with app.app_context():
            legacy_centre = add_centre(district=None, tehsil=None)
            crop = db.session.get(Crop, loc["crop_id"])
            legacy_slot = add_slot(legacy_centre, crop, hour=10,
                                   slot_date=date.today() + timedelta(days=5))
            db.session.commit()
            legacy_slot_id = legacy_slot.id
        add_farmer("loc-j-farmer", district="Mirzapur", tehsil="Mirzapur Sadar")
        db.session.commit()

        resp = call_api(client, "loc-j-farmer", "GET", "/api/slots")
        assert resp.status_code == 200, resp.get_json()
        rows = [s for s in resp.get_json()["slots"] if s["id"] == legacy_slot_id]
        assert rows, "legacy slot missing from farmer catalogue"
        assert rows[0]["centre_district"] is None
        assert rows[0]["centre_tehsil"] is None
        # Nothing to match against => ineligible, but the payload serialises fine.
        assert rows[0]["location_eligible"] is False






