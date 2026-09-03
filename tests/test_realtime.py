"""Tests for Task 10 Realtime Queue Updates (Flask-SocketIO)."""

from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

import pytest
from app.extensions import db, socketio
from app.models import (
    UserRole,
    User,
    Centre,
    Crop,
    Slot,
    SlotStatus,
    Booking,
    BookingStatus,
    Farmer,
    Staff,
)
from app.services.booking_service import create_booking, cancel_booking


@pytest.fixture
def realtime_test_data(app):
    """Fixture creating users, centre, crop, slot, and farmers for realtime tests."""
    with app.app_context():
        # 1. Users
        u1 = User(supabase_user_id="farmer-rt-1", role=UserRole.FARMER, is_active=True)
        u2 = User(supabase_user_id="farmer-rt-2", role=UserRole.FARMER, is_active=True)
        u_staff = User(supabase_user_id="staff-rt-1", role=UserRole.STAFF, is_active=True)
        db.session.add_all([u1, u2, u_staff])
        db.session.commit()

        # 2. Centre & Crop
        centre = Centre(
            name="Realtime Mandi",
            location="City RT",
            opening_time=time(8, 0),
            closing_time=time(18, 0),
            daily_capacity=100,
            is_active=True,
            average_processing_minutes=15,
        )
        crop = Crop(name="Paddy RT", is_active=True)
        db.session.add_all([centre, crop])
        db.session.commit()

        # 3. Slot
        d_target = date.today() + timedelta(days=1)
        slot = Slot(
            centre_id=centre.id,
            crop_id=crop.id,
            slot_date=d_target,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        db.session.add(slot)
        db.session.commit()

        # 4. Farmers
        f1 = Farmer(user_id=u1.id, name="Farmer One RT", phone="9990000001", city="City 1", state="State 1")
        f2 = Farmer(user_id=u2.id, name="Farmer Two RT", phone="9990000002", city="City 2", state="State 2")
        db.session.add_all([f1, f2])
        db.session.commit()

        # 5. Staff
        staff = Staff(user_id=u_staff.id, centre_id=centre.id, name="Staff RT", phone="9991111111")
        db.session.add(staff)
        db.session.commit()

        # 6. Pre-existing booking for Farmer 1
        b1 = Booking(
            farmer_id=f1.id,
            slot_id=slot.id,
            token_number="K-0001",
            status=BookingStatus.CONFIRMED
        )
        db.session.add(b1)
        db.session.commit()

        return {
            "u1_id": u1.id,
            "u2_id": u2.id,
            "u_staff_id": u_staff.id,
            "centre_id": centre.id,
            "crop_id": crop.id,
            "slot_id": slot.id,
            "f1_id": f1.id,
            "f2_id": f2.id,
            "b1_id": b1.id,
            "d_target": d_target,
        }


class TestRealtimeQueue:
    """Test suite for Flask-SocketIO /queue namespace and realtime queue update events."""

    def test_socket_connection(self, app):
        """Verify SocketIO client can connect to /queue namespace."""
        client = socketio.test_client(app, namespace="/queue")
        assert client.is_connected(namespace="/queue")
        client.disconnect(namespace="/queue")

    def test_farmer_subscribe_own_booking_success(self, app, realtime_test_data):
        """Farmer can successfully subscribe to their own booking room."""
        client = socketio.test_client(app, namespace="/queue")
        b1_id = realtime_test_data["b1_id"]

        with patch("app.queue.events.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = "farmer-rt-1"
            mock_vt.return_value = mock_user

            # Emit subscribe_queue event
            res = client.emit("subscribe_queue", {"booking_id": b1_id, "token": "valid-token"}, namespace="/queue", callback=True)
            assert res is not None
            assert res.get("status") == "subscribed"
            assert res.get("booking_id") == b1_id

        client.disconnect(namespace="/queue")

    def test_farmer_subscribe_other_farmer_booking_rejected(self, app, realtime_test_data):
        """Farmer 2 cannot subscribe to Farmer 1's booking room."""
        client = socketio.test_client(app, namespace="/queue")
        b1_id = realtime_test_data["b1_id"]

        with patch("app.queue.events.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = "farmer-rt-2"  # Farmer 2
            mock_vt.return_value = mock_user

            res = client.emit("subscribe_queue", {"booking_id": b1_id, "token": "valid-token"}, namespace="/queue", callback=True)
            assert res is not None
            assert "error" in res
            assert "Booking not found or access denied" in res["error"]

        client.disconnect(namespace="/queue")

    def test_staff_subscribe_centre_queue_success(self, app, realtime_test_data):
        """STAFF user can subscribe to centre queue room."""
        client = socketio.test_client(app, namespace="/queue")
        c_id = realtime_test_data["centre_id"]
        d_str = realtime_test_data["d_target"].isoformat()

        with patch("app.queue.events.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = "staff-rt-1"
            mock_vt.return_value = mock_user

            res = client.emit("subscribe_centre_queue", {"centre_id": c_id, "date": d_str, "token": "valid-token"}, namespace="/queue", callback=True)
            assert res is not None
            assert res.get("status") == "subscribed"
            assert res.get("centre_id") == c_id

        client.disconnect(namespace="/queue")

    def test_farmer_subscribe_centre_queue_rejected(self, app, realtime_test_data):
        """Farmer user cannot subscribe to staff centre queue room."""
        client = socketio.test_client(app, namespace="/queue")
        c_id = realtime_test_data["centre_id"]
        d_str = realtime_test_data["d_target"].isoformat()

        with patch("app.queue.events.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = "farmer-rt-1"
            mock_vt.return_value = mock_user

            res = client.emit("subscribe_centre_queue", {"centre_id": c_id, "date": d_str, "token": "valid-token"}, namespace="/queue", callback=True)
            assert res is not None
            assert "error" in res
            assert "STAFF or ADMIN role required" in res["error"]

        client.disconnect(namespace="/queue")

    def test_event_emission_on_booking_creation_and_cancellation(self, app, realtime_test_data):
        """Verify queue_updated event is emitted post-commit when booking is created or cancelled."""
        client = socketio.test_client(app, namespace="/queue")

        # 1. Staff connects and subscribes to centre queue room
        c_id = realtime_test_data["centre_id"]
        d_str = realtime_test_data["d_target"].isoformat()

        with patch("app.queue.events.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = "staff-rt-1"
            mock_vt.return_value = mock_user
            client.emit("subscribe_centre_queue", {"centre_id": c_id, "date": d_str, "token": "valid-token"}, namespace="/queue", callback=True)

        # Clear received events queue
        client.get_received(namespace="/queue")

        # 2. Farmer 2 creates booking
        u2_id = realtime_test_data["u2_id"]
        slot_id = realtime_test_data["slot_id"]

        with app.app_context():
            new_b = create_booking(user_id=u2_id, slot_id=slot_id)
            new_b_id = new_b.id

        # Inspect SocketIO events received by staff client
        events = client.get_received(namespace="/queue")
        assert len(events) >= 1
        queue_events = [e for e in events if e["name"] == "queue_updated"]
        assert len(queue_events) >= 1
        payload = queue_events[0]["args"][0]
        assert payload["centre_id"] == c_id
        assert payload["slot_date"] == d_str
        assert payload["reason"] == "BOOKING_CREATED"

        # 3. Farmer 2 cancels booking
        client.get_received(namespace="/queue")
        with app.app_context():
            cancel_booking(booking_id=new_b_id, user_id=u2_id)

        events_cancel = client.get_received(namespace="/queue")
        queue_events_cancel = [e for e in events_cancel if e["name"] == "queue_updated"]
        assert len(queue_events_cancel) >= 1
        payload_cancel = queue_events_cancel[0]["args"][0]
        assert payload_cancel["reason"] == "BOOKING_CANCELLED"

        client.disconnect(namespace="/queue")

    def test_multi_farmer_queue_propagation_on_cancellation(self, app, client, realtime_test_data):
        """Verify Farmer A cancellation emits queue_updated to centre/date room, received by Farmer B and Farmer C."""
        with app.app_context():
            slot_id = realtime_test_data["slot_id"]
            u3 = User(supabase_user_id="farmer-rt-3", role=UserRole.FARMER, is_active=True)
            db.session.add(u3)
            db.session.commit()

            f3 = Farmer(user_id=u3.id, name="Farmer Three RT", phone="9990000003", city="City 3", state="State 3")
            db.session.add(f3)
            db.session.commit()

            # Create bookings: Farmer 1 (b1=K-0001), Farmer 2 (b2=K-0002), Farmer 3 (b3=K-0003)
            b2 = Booking(farmer_id=realtime_test_data["f2_id"], slot_id=slot_id, token_number="K-0002", status=BookingStatus.CONFIRMED)
            b3 = Booking(farmer_id=f3.id, slot_id=slot_id, token_number="K-0003", status=BookingStatus.CONFIRMED)
            db.session.add_all([b2, b3])
            db.session.commit()

            b1_id = realtime_test_data["b1_id"]
            b2_id = b2.id
            b3_id = b3.id
            u1_id = realtime_test_data["u1_id"]

        # Socket client for Farmer 2
        client_f2 = socketio.test_client(app, namespace="/queue")
        with patch("app.queue.events.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = "farmer-rt-2"
            mock_vt.return_value = mock_user
            client_f2.emit("subscribe_queue", {"booking_id": b2_id, "token": "valid-token"}, namespace="/queue", callback=True)

        # Socket client for Farmer 3
        client_f3 = socketio.test_client(app, namespace="/queue")
        with patch("app.queue.events.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = "farmer-rt-3"
            mock_vt.return_value = mock_user
            client_f3.emit("subscribe_queue", {"booking_id": b3_id, "token": "valid-token"}, namespace="/queue", callback=True)

        # Clear initial events
        client_f2.get_received(namespace="/queue")
        client_f3.get_received(namespace="/queue")

        # Farmer 1 cancels booking
        with app.app_context():
            cancel_booking(booking_id=b1_id, user_id=u1_id)

        # Verify Farmer 2 received queue_updated
        events_f2 = client_f2.get_received(namespace="/queue")
        assert any(e["name"] == "queue_updated" and e["args"][0]["reason"] == "BOOKING_CANCELLED" for e in events_f2)

        # Verify Farmer 3 received queue_updated
        events_f3 = client_f3.get_received(namespace="/queue")
        assert any(e["name"] == "queue_updated" and e["args"][0]["reason"] == "BOOKING_CANCELLED" for e in events_f3)

        # Verify Farmer 2 & 3 REST API queue positions shifted forward
        su2 = MagicMock()
        su2.id = "farmer-rt-2"
        su2.user_metadata = {"role": UserRole.FARMER}

        su3 = MagicMock()
        su3.id = "farmer-rt-3"
        su3.user_metadata = {"role": UserRole.FARMER}

        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_c = MagicMock()
            mock_gc.return_value = mock_c

            mock_c.auth.get_user.return_value.user = su2
            r2 = client.get(f"/api/queue/my/{b2_id}", headers={"Authorization": "Bearer token"})
            assert r2.status_code == 200
            assert r2.get_json()["queue_position"] == 1
            assert r2.get_json()["farmers_ahead"] == 0

            mock_c.auth.get_user.return_value.user = su3
            r3 = client.get(f"/api/queue/my/{b3_id}", headers={"Authorization": "Bearer token"})
            assert r3.status_code == 200
            assert r3.get_json()["queue_position"] == 2
            assert r3.get_json()["farmers_ahead"] == 1

        client_f2.disconnect(namespace="/queue")
        client_f3.disconnect(namespace="/queue")

