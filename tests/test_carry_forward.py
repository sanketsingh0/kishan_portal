"""Tests for Staff-Controlled Next-Day Carry-Forward (part 1: fixtures)."""

from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models import (
    Booking, BookingStatus, BookingCarryForward, Centre, Crop, Farmer,
    Procurement, ProcurementStatus, Slot, SlotStatus, Staff, User, UserRole,
)


def make_mock_user(user_id="x"):
    u = MagicMock()
    u.id = user_id
    return u


def auth_header(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


def api_call(client, supa_id, method, url, payload=None):
    su = make_mock_user(user_id=supa_id)
    with patch("app.auth.service.get_supabase_client") as mock_gc:
        mc = MagicMock()
        mock_gc.return_value = mc
        mc.auth.get_user.return_value.user = su
        if method == "GET":
            return client.get(url, headers=auth_header())
        return client.post(url, json=payload or {}, headers=auth_header())


@pytest.fixture
def cf_data(app):
    with app.app_context():
        u_f1 = User(supabase_user_id="cf-f1", role=UserRole.FARMER,
                    is_active=True)
        u_f2 = User(supabase_user_id="cf-f2", role=UserRole.FARMER,
                    is_active=True)
        u_f3 = User(supabase_user_id="cf-f3", role=UserRole.FARMER,
                    is_active=True)
        u_staff = User(supabase_user_id="cf-staff", role=UserRole.STAFF,
                       is_active=True)
        u_staff2 = User(supabase_user_id="cf-staff2", role=UserRole.STAFF,
                        is_active=True)
        u_admin = User(supabase_user_id="cf-admin", role=UserRole.ADMIN,
                       is_active=True)
        db.session.add_all([u_f1, u_f2, u_f3, u_staff, u_staff2, u_admin])
        db.session.flush()
        f1 = Farmer(user_id=u_f1.id, name="CF Farmer One", phone="9100000001")
        f2 = Farmer(user_id=u_f2.id, name="CF Farmer Two", phone="9100000002")
        f3 = Farmer(user_id=u_f3.id, name="CF Farmer Three", phone="9100000003")
        db.session.add_all([f1, f2, f3])
        c1 = Centre(name="CF Centre 1", location="Loc 1",
                    opening_time=time(8, 0), closing_time=time(18, 0),
                    daily_capacity=100, is_active=True)
        c2 = Centre(name="CF Centre 2", location="Loc 2",
                    opening_time=time(8, 0), closing_time=time(18, 0),
                    daily_capacity=100, is_active=True)
        db.session.add_all([c1, c2])
        db.session.flush()
        st1 = Staff(user_id=u_staff.id, name="CF Staff", centre_id=c1.id)
        st2 = Staff(user_id=u_staff2.id, name="CF Staff 2", centre_id=c2.id)
        db.session.add_all([st1, st2])
        crop = Crop(name="CF Wheat", category="Cereal", is_active=True)
        db.session.add(crop)
        db.session.flush()
        src = date.today() + timedelta(days=1)
        tgt = src + timedelta(days=1)
        s_src = Slot(centre_id=c1.id, crop_id=crop.id, slot_date=src,
                     start_time=time(9, 0), end_time=time(10, 0),
                     capacity=10, status=SlotStatus.OPEN)
        s_tgt = Slot(centre_id=c1.id, crop_id=crop.id, slot_date=tgt,
                     start_time=time(9, 0), end_time=time(10, 0),
                     capacity=10, status=SlotStatus.OPEN)
        s_other = Slot(centre_id=c2.id, crop_id=crop.id, slot_date=src,
                       start_time=time(9, 0), end_time=time(10, 0),
                       capacity=10, status=SlotStatus.OPEN)
        db.session.add_all([s_src, s_tgt, s_other])
        db.session.flush()
        b1 = Booking(farmer_id=f1.id, slot_id=s_src.id,
                     status=BookingStatus.CONFIRMED, token_number="K-0001")
        b2 = Booking(farmer_id=f2.id, slot_id=s_src.id,
                     status=BookingStatus.CONFIRMED, token_number="K-0002")
        b3 = Booking(farmer_id=f3.id, slot_id=s_src.id,
                     status=BookingStatus.CONFIRMED, token_number="K-0003")
        db.session.add_all([b1, b2, b3])
        db.session.commit()
        yield {"src": src, "tgt": tgt, "s_src": s_src, "s_tgt": s_tgt,
               "s_other": s_other, "b1": b1, "b2": b2, "b3": b3,
               "c1": c1, "c2": c2, "crop": crop,
               "f1": f1, "f2": f2, "f3": f3}


class TestEligibleAuth:
    def test_staff_views_eligible(self, client, app, cf_data):
        r = api_call(client, "cf-staff", "GET",
                     f"/api/staff/carry-forward/eligible?date={cf_data['src']}")
        assert r.status_code == 200
        assert r.get_json()["eligible_count"] == 3

    def test_farmer_forbidden(self, client, app, cf_data):
        r = api_call(client, "cf-f1", "GET",
                     f"/api/staff/carry-forward/eligible?date={cf_data['src']}")
        assert r.status_code == 403

    def test_admin_any_centre(self, client, app, cf_data):
        r = api_call(client, "cf-admin", "GET",
                     "/api/staff/carry-forward/eligible"
                     f"?date={cf_data['src']}&centre_id={cf_data['c1'].id}")
        assert r.status_code == 200
        assert r.get_json()["eligible_count"] == 3

    def test_other_centre_rejected(self, client, app, cf_data):
        with app.app_context():
            u = User.query.filter_by(supabase_user_id="cf-f1").first()
            f = Farmer.query.filter_by(user_id=u.id).first()
            ob = Booking(farmer_id=f.id, slot_id=cf_data["s_other"].id,
                         status=BookingStatus.CONFIRMED, token_number="K-0009")
            db.session.add(ob)
            db.session.commit()
            oid = ob.id
        r = api_call(client, "cf-staff", "POST", "/api/staff/carry-forward",
                     {"booking_ids": [oid],
                      "target_date": str(cf_data["tgt"]),
                      "reason": "Centre closed"})
        assert r.status_code == 400

class TestCarryExecution:
    def _post(self, client, who, bids, tgt, reason="Centre closed",
              extra=None):
        payload = {"booking_ids": bids, "target_date": str(tgt),
                   "reason": reason}
        if extra:
            payload.update(extra)
        return api_call(client, who, "POST", "/api/staff/carry-forward",
                        payload)

    def test_success_new_token_link_audit_queue(self, client, app, cf_data):
        old_token = cf_data["b1"].token_number
        r = self._post(client, "cf-staff", [cf_data["b1"].id], cf_data["tgt"])
        assert r.status_code == 200
        data = r.get_json()
        assert data["successful_count"] == 1
        new_token = data["successful"][0]["new_token"]
        assert new_token and new_token.startswith("K-")
        assert data["successful"][0]["new_booking_id"] != cf_data["b1"].id
        with app.app_context():
            orig = db.session.get(Booking, cf_data["b1"].id)
            assert orig.status == BookingStatus.CARRIED_FORWARD
            new = db.session.get(Booking,
                                 data["successful"][0]["new_booking_id"])
            assert new.slot.slot_date == cf_data["tgt"]
            assert new.procurement is None
            link = BookingCarryForward.query.filter_by(
                original_booking_id=orig.id).first()
            assert link is not None and link.new_booking_id == new.id
            from app.models import AuditLog
            logs = AuditLog.query.filter_by(
                action="CARRY_FORWARD_BOOKING").all()
            assert any(st.entity_id == orig.id for st in logs)
            from app.models import SmartQueuePass
            assert SmartQueuePass.query.filter_by(
                booking_id=new.id).first() is not None
            from app.services.queue_service import get_centre_queue
            q_old = get_centre_queue(cf_data["c1"].id, cf_data["src"])
            assert cf_data["b1"].id not in [q["booking_id"]
                                            for q in q_old["queue"]]
            q_new = get_centre_queue(cf_data["c1"].id, cf_data["tgt"])
            assert new.id in [q["booking_id"] for q in q_new["queue"]]

    def test_terminal_statuses_excluded(self, client, app, cf_data):
        # f3 already holds b3 on the source slot, so the extra REJECTED
        # procurement booking must belong to a fresh farmer to respect the
        # active-booking unique index; the TIME_CONFLICT path is covered
        # separately below.
        with app.app_context():
            from app.models import User as _User, Farmer as _Farmer
            ux = _User(supabase_user_id="cf-fx", role=UserRole.FARMER,
                       is_active=True)
            db.session.add(ux)
            db.session.flush()
            fx = _Farmer(user_id=ux.id, name="CF Extra", phone="9100000090")
            db.session.add(fx)
            db.session.flush()
            rj = Booking(farmer_id=fx.id, slot_id=cf_data["s_src"].id,
                         status=BookingStatus.CONFIRMED, token_number="K-0008")
            db.session.add(rj)
            db.session.flush()
            db.session.add(Procurement(
                booking_id=rj.id,
                procurement_status=ProcurementStatus.REJECTED))
            db.session.commit()
            db.session.expire_all()
            rj_id = rj.id
        r = self._post(client, "cf-staff", [rj_id], cf_data["tgt"])
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["successful_count"] == 0
        assert r.get_json()["failed"][0]["code"] == "NOT_ELIGIBLE"

    def test_completed_cancelled_rejected_never_eligible(self, client, app,
                                                         cf_data):
        from app.services.carry_forward_service import check_booking_eligibility
        with app.app_context():
            from app.models import User as _U2, Farmer as _F2
            u2 = _U2(supabase_user_id="cf-fy", role=UserRole.FARMER,
                     is_active=True)
            db.session.add(u2)
            db.session.flush()
            fy = _F2(user_id=u2.id, name="CF Extra2", phone="9100000091")
            db.session.add(fy)
            db.session.flush()
            b2 = db.session.get(Booking, cf_data["b2"].id)
            b2.status = BookingStatus.COMPLETED
            assert check_booking_eligibility(
                b2, cf_data["src"], cf_data["c1"].id)[0] is False
            b3 = db.session.get(Booking, cf_data["b3"].id)
            b3.status = BookingStatus.CANCELLED
            assert check_booking_eligibility(
                b3, cf_data["src"], cf_data["c1"].id)[0] is False
            db.session.rollback()
            rj = Booking(farmer_id=fy.id, slot_id=cf_data["s_src"].id,
                         status=BookingStatus.CONFIRMED, token_number="K-0090")
            db.session.add(rj)
            db.session.flush()
            db.session.add(Procurement(
                booking_id=rj.id,
                procurement_status=ProcurementStatus.REJECTED))
            db.session.flush()
            ok, why = check_booking_eligibility(rj, cf_data["src"],
                                                cf_data["c1"].id)
            assert ok is False and "REJECTED" in why
            db.session.rollback()

    def test_noshow_and_carriedforward_never_eligible(self, client, app,
                                                      cf_data):
        from app.services.carry_forward_service import check_booking_eligibility
        with app.app_context():
            b1 = db.session.get(Booking, cf_data["b1"].id)
            b1.status = BookingStatus.NO_SHOW
            assert check_booking_eligibility(
                b1, cf_data["src"], cf_data["c1"].id)[0] is False
            b1.status = BookingStatus.CARRIED_FORWARD
            assert check_booking_eligibility(
                b1, cf_data["src"], cf_data["c1"].id)[0] is False
            db.session.rollback()

    def test_in_progress_excluded(self, client, app, cf_data):
        with app.app_context():
            db.session.add(Procurement(
                booking_id=cf_data["b1"].id,
                procurement_status=ProcurementStatus.IN_PROGRESS))
            db.session.commit()
        r = self._post(client, "cf-staff", [cf_data["b1"].id], cf_data["tgt"])
        assert r.get_json()["successful_count"] == 0

    def test_duplicate_request_idempotent(self, client, app, cf_data):
        r1 = self._post(client, "cf-staff", [cf_data["b1"].id], cf_data["tgt"])
        assert r1.get_json()["successful_count"] == 1
        r2 = self._post(client, "cf-staff", [cf_data["b1"].id], cf_data["tgt"])
        assert r2.get_json()["successful_count"] == 0
        with app.app_context():
            assert BookingCarryForward.query.filter_by(
                original_booking_id=cf_data["b1"].id).count() == 1

    def test_full_slot_rejected(self, client, app, cf_data):
        with app.app_context():
            tgt = db.session.get(Slot, cf_data["s_tgt"].id)
            tgt.capacity = 0
            db.session.commit()
            db.session.expire_all()
        r = self._post(client, "cf-staff", [cf_data["b1"].id], cf_data["tgt"])
        assert r.get_json()["failed"][0]["code"] == "TARGET_SLOT_FULL"

    def test_dup_overlap_and_rollback(self, client, app, cf_data):
        # Duplicate target slot booking is rejected cleanly.
        with app.app_context():
            from app.models import User as _U3, Farmer as _F3
            u3 = _U3(supabase_user_id="cf-fz", role=UserRole.FARMER,
                     is_active=True)
            db.session.add(u3)
            db.session.flush()
            fz = _F3(user_id=u3.id, name="CF Extra3", phone="9100000092")
            db.session.add(fz)
            db.session.flush()
            pre = Booking(farmer_id=cf_data["f1"].id,
                          slot_id=cf_data["s_tgt"].id,
                          status=BookingStatus.CONFIRMED,
                          token_number="K-0050")
            db.session.add(pre)
            db.session.commit()
            db.session.expire_all()
        r = self._post(client, "cf-staff", [cf_data["b1"].id], cf_data["tgt"])
        assert r.get_json()["failed"][0]["code"] == "DUPLICATE_BOOKING"
        # Transaction rollback: a forced failure leaves no partial rows.
        with app.app_context():
            from app.services import carry_forward_execute as _exe
            real_gen = _exe.generate_token_for_booking
            def _boom(slot):
                raise RuntimeError("forced token failure")
            _exe.generate_token_for_booking = _boom
            try:
                out = _exe.carry_forward_bookings(
                    actor_user=User.query.filter_by(
                        supabase_user_id="cf-staff").first(),
                    centre_id=cf_data["c1"].id,
                    booking_ids=[cf_data["b2"].id],
                    target_date=str(cf_data["tgt"]),
                    reason="Operational issue")
            finally:
                _exe.generate_token_for_booking = real_gen
            assert out["successful_count"] == 0
            b2 = db.session.get(Booking, cf_data["b2"].id)
            assert b2.status == BookingStatus.CONFIRMED
            assert BookingCarryForward.query.filter_by(
                original_booking_id=b2.id).first() is None

    def test_centre_isolation_overlap_qr_and_notify(self, client, app,
                                                    cf_data):
        # Overlap on target date rejected; old QR cancelled; new QR created;
        # notification + audit emitted for successes.
        with app.app_context():
            from app.models import Slot as _Slot, Crop as _Crop
            s_ov = _Slot(centre_id=cf_data["c1"].id,
                         crop_id=cf_data["crop"].id,
                         slot_date=cf_data["tgt"],
                         start_time=__import__("datetime").time(9, 30),
                         end_time=__import__("datetime").time(10, 30),
                         capacity=10, status=SlotStatus.OPEN)
            db.session.add(s_ov)
            db.session.flush()
            ov = Booking(farmer_id=cf_data["f1"].id, slot_id=s_ov.id,
                         status=BookingStatus.CONFIRMED,
                         token_number="K-0060")
            db.session.add(ov)
            db.session.commit()
            db.session.expire_all()
        r = self._post(client, "cf-staff", [cf_data["b1"].id], cf_data["tgt"])
        assert r.get_json()["failed"][0]["code"] == "TIME_CONFLICT"
        r2 = self._post(client, "cf-staff", [cf_data["b2"].id], cf_data["tgt"])
        assert r2.get_json()["successful_count"] == 1
        with app.app_context():
            from app.models import (SmartQueuePass as _P,
                                    SmartQueuePassStatus as _PS,
                                    Notification as _N, AuditLog as _A)
            orig = db.session.get(Booking, cf_data["b2"].id)
            new_id = r2.get_json()["successful"][0]["new_booking_id"]
            old_pass = _P.query.filter_by(booking_id=orig.id).first()
            assert old_pass is None or old_pass.status != "ACTIVE"
            new_pass = _P.query.filter_by(booking_id=new_id).first()
            assert new_pass is not None
            assert new_pass.secure_pass_id != (
                old_pass.secure_pass_id if old_pass else None)
            assert _N.query.filter_by(booking_id=new_id).first() is not None
            assert _A.query.filter_by(
                action="CARRY_FORWARD_BOOKING",
                entity_id=orig.id).first() is not None


class TestStrictNextDay:
    def _post(self, client, who, bids, tgt, reason="Centre closed",
              extra=None):
        payload = {"booking_ids": bids, "target_date": str(tgt),
                   "reason": reason}
        if extra:
            payload.update(extra)
        return api_call(client, who, "POST", "/api/staff/carry-forward",
                        payload)

    def test_next_day_allowed(self, client, app, cf_data):
        r = self._post(client, "cf-staff", [cf_data["b1"].id],
                       cf_data["tgt"])
        assert r.status_code == 200
        assert r.get_json()["successful_count"] == 1

    def test_two_days_ahead_rejected(self, client, app, cf_data):
        far = cf_data["src"] + timedelta(days=2)
        r = self._post(client, "cf-staff", [cf_data["b1"].id], far)
        assert r.status_code == 400
        body = r.get_json()
        assert body["error"] == "Validation failed"
        assert "next day" in body["message"].lower()

    def test_far_future_rejected(self, client, app, cf_data):
        far = cf_data["src"] + timedelta(days=7)
        r = self._post(client, "cf-staff", [cf_data["b1"].id], far)
        assert r.status_code == 400
        assert "next day" in r.get_json()["message"].lower()

    def test_same_date_rejected(self, client, app, cf_data):
        r = self._post(client, "cf-staff", [cf_data["b1"].id],
                       cf_data["src"])
        assert r.status_code == 400
        assert "next day" in r.get_json()["message"].lower()

    def test_earlier_date_rejected(self, client, app, cf_data):
        earlier = cf_data["src"] - timedelta(days=1)
        r = self._post(client, "cf-staff", [cf_data["b1"].id], earlier)
        assert r.status_code == 400
        assert "next day" in r.get_json()["message"].lower()

    def test_service_level_rejects_non_next_day(self, app, cf_data):
        from app.services.carry_forward_execute import (
            carry_forward_bookings)
        from app.services.carry_forward_service import (
            CarryForwardValidationError)
        with app.app_context():
            actor = User.query.filter_by(
                supabase_user_id="cf-staff").first()
            with pytest.raises(CarryForwardValidationError) as exc:
                carry_forward_bookings(
                    actor_user=actor,
                    centre_id=cf_data["c1"].id,
                    booking_ids=[cf_data["b1"].id],
                    target_date=str(cf_data["src"] + timedelta(days=2)),
                    reason="Centre closed")
            assert "next day" in str(exc.value).lower()

