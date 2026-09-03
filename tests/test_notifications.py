"""Unit and Integration test suite for Task 13 — Notification System.

Tests Notification and PushSubscription models, service logic, API endpoints,
automatic triggers (booking, delay, procurement, payment), Socket.IO realtime events,
and security access controls.
"""

import pytest
from datetime import date, time, datetime, timezone
from unittest.mock import patch, MagicMock
from app.extensions import db
from app.models import (
    User,
    UserRole,
    Farmer,
    Staff,
    Centre,
    Crop,
    Slot,
    SlotStatus,
    Booking,
    BookingStatus,
    Notification,
    NotificationType,
    PushSubscription,
)
from app.services.notification_service import (
    create_notification,
    get_user_notifications,
    get_unread_count,
    mark_notification_read,
    mark_all_notifications_read,
    save_push_subscription,
    remove_push_subscription,
    NotificationError,
    NotificationNotFoundError,
    NotificationValidationError,
)
from app.services.booking_service import create_booking, cancel_booking
from app.services.delay_service import create_delay, update_delay, cancel_delay
from app.services.procurement_service import create_procurement, update_procurement
from app.services.payment_service import create_payment, update_payment


# --- Fixtures ------------------------------------------------------------------

@pytest.fixture
def test_users(app):
    """Create test users (farmer_user, farmer_user2, staff_user)."""
    with app.app_context():
        u_farmer1 = User(
            id=101,
            supabase_user_id="sub-farmer-101",
            role=UserRole.FARMER,
            is_active=True,
        )
        u_farmer2 = User(
            id=102,
            supabase_user_id="sub-farmer-102",
            role=UserRole.FARMER,
            is_active=True,
        )
        u_staff = User(
            id=103,
            supabase_user_id="sub-staff-103",
            role=UserRole.STAFF,
            is_active=True,
        )
        db.session.add_all([u_farmer1, u_farmer2, u_staff])
        db.session.commit()

        f1 = Farmer(id=1, user_id=101, name="Farmer One", state="Punjab", city="Ludhiana")
        f2 = Farmer(id=2, user_id=102, name="Farmer Two", state="Punjab", city="Amritsar")
        s1 = Staff(id=1, user_id=103, name="Staff One", centre_id=1)
        db.session.add_all([f1, f2, s1])
        db.session.commit()

        yield u_farmer1, u_farmer2, u_staff


@pytest.fixture
def setup_domain(app, test_users):
    """Setup centre, crop, slot, and bookings for domain testing."""
    with app.app_context():
        c1 = Centre(id=1, name="Ludhiana Mandi", location="Ludhiana, Punjab", daily_capacity=100, is_active=True)
        c2 = Centre(id=2, name="Amritsar Mandi", location="Amritsar, Punjab", daily_capacity=100, is_active=True)
        crop1 = Crop(id=1, name="Wheat", is_active=True)
        db.session.add_all([c1, c2, crop1])
        db.session.commit()

        d1 = date(2026, 9, 20)
        slot1 = Slot(
            id=1,
            centre_id=1,
            crop_id=1,
            slot_date=d1,
            start_time=time(9, 0),
            end_time=time(12, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        slot2 = Slot(
            id=2,
            centre_id=1,
            crop_id=1,
            slot_date=d1,
            start_time=time(13, 0),
            end_time=time(16, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        slot3 = Slot(
            id=3,
            centre_id=2,
            crop_id=1,
            slot_date=d1,
            start_time=time(9, 0),
            end_time=time(12, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        d2 = date(2026, 9, 21)
        slot4 = Slot(
            id=4,
            centre_id=1,
            crop_id=1,
            slot_date=d2,
            start_time=time(9, 0),
            end_time=time(12, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        db.session.add_all([slot1, slot2, slot3, slot4])
        db.session.commit()

        b1 = Booking(
            id=1,
            farmer_id=1,
            slot_id=1,
            booking_date=datetime.now(timezone.utc),
            status=BookingStatus.CONFIRMED,
            token_number="LDH-0001",
        )
        b2 = Booking(
            id=2,
            farmer_id=2,
            slot_id=2,
            booking_date=datetime.now(timezone.utc),
            status=BookingStatus.CONFIRMED,
            token_number="LDH-0002",
        )
        db.session.add_all([b1, b2])
        db.session.commit()

        c1_id, c2_id = c1.id, c2.id
        slot1_id, slot2_id, slot3_id, slot4_id = slot1.id, slot2.id, slot3.id, slot4.id
        b1_id, b2_id = b1.id, b2.id

        return {
            "c1_id": c1_id,
            "c2_id": c2_id,
            "slot1_id": slot1_id,
            "slot2_id": slot2_id,
            "slot3_id": slot3_id,
            "slot4_id": slot4_id,
            "b1_id": b1_id,
            "b2_id": b2_id,
        }


def make_auth_call(client, method, url, sub_id, json_data=None):
    """Helper to execute API request with mocked authentication."""
    with patch("app.auth.decorators.verify_token") as mock_vt:
        mock_user = MagicMock()
        mock_user.id = sub_id
        mock_vt.return_value = mock_user

        headers = {"Authorization": "Bearer mock-token"}
        if method.upper() == "GET":
            return client.get(url, headers=headers)
        elif method.upper() == "POST":
            return client.post(url, json=json_data, headers=headers)
        elif method.upper() == "PUT":
            return client.put(url, json=json_data, headers=headers)
        elif method.upper() == "DELETE":
            return client.delete(url, headers=headers)


# --- 1. Notification Model Tests -----------------------------------------------

def test_notification_model_creation(app, test_users):
    """Verify notification model default attributes, relationships, and serialization."""
    with app.app_context():
        u_farmer1 = test_users[0]
        n = Notification(
            user_id=u_farmer1.id,
            notification_type=NotificationType.BOOKING_CONFIRMED,
            title="Booking Confirmed",
            message="Your token is K-1001",
            is_read=False,
        )
        db.session.add(n)
        db.session.commit()

        assert n.id is not None
        assert n.is_read is False
        assert n.read_at is None
        assert n.created_at is not None

        dict_data = n.to_dict()
        assert dict_data["id"] == n.id
        assert dict_data["user_id"] == u_farmer1.id
        assert dict_data["title"] == "Booking Confirmed"
        assert dict_data["is_read"] is False


def test_notification_read_timestamp(app, test_users):
    """Verify mark_notification_read sets read_at timestamp."""
    with app.app_context():
        u_farmer1 = test_users[0]
        n = create_notification(u_farmer1.id, NotificationType.SYSTEM, "Test", "Test Message")
        assert n.is_read is False
        assert n.read_at is None

        read_n = mark_notification_read(n.id, u_farmer1.id)
        assert read_n.is_read is True
        assert read_n.read_at is not None


# --- 2. Notification Authorization & Service Tests ----------------------------

def test_service_create_and_get_user_notifications(app, test_users):
    """Verify user can only fetch their own notifications."""
    with app.app_context():
        u1, u2, _ = test_users
        create_notification(u1.id, NotificationType.SYSTEM, "Msg 1 for U1", "Details")
        create_notification(u1.id, NotificationType.SYSTEM, "Msg 2 for U1", "Details")
        create_notification(u2.id, NotificationType.SYSTEM, "Msg 1 for U2", "Details")

        notifs_u1 = get_user_notifications(u1.id)
        notifs_u2 = get_user_notifications(u2.id)

        assert len(notifs_u1) == 2
        assert len(notifs_u2) == 1
        assert all(n.user_id == u1.id for n in notifs_u1)
        assert all(n.user_id == u2.id for n in notifs_u2)


def test_mark_other_user_notification_rejected(app, test_users):
    """Verify farmer cannot mark another user's notification as read."""
    with app.app_context():
        u1, u2, _ = test_users
        n1 = create_notification(u1.id, NotificationType.SYSTEM, "Private U1", "Message")

        with pytest.raises(NotificationNotFoundError):
            mark_notification_read(n1.id, user_id=u2.id)


def test_mark_all_read(app, test_users):
    """Verify mark_all_notifications_read updates only target user's unread records."""
    with app.app_context():
        u1, u2, _ = test_users
        create_notification(u1.id, NotificationType.SYSTEM, "U1-1", "Msg")
        create_notification(u1.id, NotificationType.SYSTEM, "U1-2", "Msg")
        create_notification(u2.id, NotificationType.SYSTEM, "U2-1", "Msg")

        assert get_unread_count(u1.id) == 2
        assert get_unread_count(u2.id) == 1

        updated_cnt = mark_all_notifications_read(u1.id)
        assert updated_cnt == 2

        assert get_unread_count(u1.id) == 0
        assert get_unread_count(u2.id) == 1


# --- 3. REST API Endpoint Tests -----------------------------------------------

def test_api_unauthenticated_rejected(client):
    """Verify 401 Unauthorized when no JWT token is provided."""
    res = client.get("/api/notifications")
    assert res.status_code == 401


def test_api_list_and_unread_count(client, test_users, app):
    """Verify GET /api/notifications and GET /api/notifications/unread-count."""
    with app.app_context():
        u1 = test_users[0]
        create_notification(u1.id, NotificationType.BOOKING_CONFIRMED, "Title 1", "Message 1")
        create_notification(u1.id, NotificationType.DELAY_UPDATE, "Title 2", "Message 2")

    res_list = make_auth_call(client, "GET", "/api/notifications", "sub-farmer-101")
    assert res_list.status_code == 200
    data_list = res_list.get_json()
    assert len(data_list["notifications"]) == 2
    assert data_list["unread_count"] == 2

    res_count = make_auth_call(client, "GET", "/api/notifications/unread-count", "sub-farmer-101")
    assert res_count.status_code == 200
    assert res_count.get_json()["unread_count"] == 2


def test_api_mark_single_and_all_read(client, test_users, app):
    """Verify PUT /api/notifications/<id>/read and PUT /api/notifications/read-all."""
    with app.app_context():
        u1 = test_users[0]
        n1 = create_notification(u1.id, NotificationType.SYSTEM, "N1", "M1")
        n2 = create_notification(u1.id, NotificationType.SYSTEM, "N2", "M2")
        notif_id = n1.id

    # Mark single
    res1 = make_auth_call(client, "PUT", f"/api/notifications/{notif_id}/read", "sub-farmer-101")
    assert res1.status_code == 200
    assert res1.get_json()["notification"]["is_read"] is True

    # Check unread count is 1
    res_count = make_auth_call(client, "GET", "/api/notifications/unread-count", "sub-farmer-101")
    assert res_count.get_json()["unread_count"] == 1

    # Mark all read
    res_all = make_auth_call(client, "PUT", "/api/notifications/read-all", "sub-farmer-101")
    assert res_all.status_code == 200
    assert res_all.get_json()["updated_count"] == 1

    # Final unread count is 0
    res_count2 = make_auth_call(client, "GET", "/api/notifications/unread-count", "sub-farmer-101")
    assert res_count2.get_json()["unread_count"] == 0


def test_api_cross_user_isolation(client, test_users, app):
    """Verify farmer 2 cannot read or mark farmer 1's notification as read via API."""
    with app.app_context():
        u1 = test_users[0]
        n1 = create_notification(u1.id, NotificationType.SYSTEM, "User 1 Secret", "M1")
        n1_id = n1.id

    # Authenticated as User 2 (Farmer 2)
    res = make_auth_call(client, "PUT", f"/api/notifications/{n1_id}/read", "sub-farmer-102")
    assert res.status_code == 404


# --- 4. Integration Triggers (Booking, Delay, Procurement, Payment) ----------

def test_booking_created_and_cancelled_triggers(app, test_users, setup_domain):
    """Verify booking confirmation and cancellation automatically generate notifications."""
    with app.app_context():
        u1, _, _ = test_users
        slot4_id = setup_domain["slot4_id"]

        # Initial notifications count
        initial_count = get_unread_count(u1.id)

        # Create new slot booking for slot 4
        b = create_booking(user_id=u1.id, slot_id=slot4_id)
        assert get_unread_count(u1.id) == initial_count + 1

        notif = get_user_notifications(u1.id, limit=1)[0]
        assert notif.notification_type == NotificationType.BOOKING_CONFIRMED
        assert "Booking Confirmed" in notif.title
        assert b.token_number in notif.message

        # Cancel booking
        cancel_booking(b.id, user_id=u1.id)
        assert get_unread_count(u1.id) == initial_count + 2

        cancel_notif = get_user_notifications(u1.id, limit=1)[0]
        assert cancel_notif.notification_type == NotificationType.BOOKING_CANCELLED
        assert "Booking Cancelled" in cancel_notif.title


def test_delay_triggers_applicable_farmers(app, test_users, setup_domain):
    """Verify delay creation notifies farmers with active bookings on matching centre/date/slot."""
    with app.app_context():
        u1, u2, _ = test_users
        c1_id = setup_domain["c1_id"]
        slot1_id = setup_domain["slot1_id"]

        # 1. Centre-wide delay on Centre 1
        create_delay(
            data={"centre_id": c1_id, "delay_date": "2026-09-20", "delay_minutes": 15, "reason": "Weather"},
            current_user_id=103,
        )
        assert get_unread_count(u1.id) >= 1
        assert get_unread_count(u2.id) >= 1

        n1 = get_user_notifications(u1.id, limit=1)[0]
        assert n1.notification_type == NotificationType.DELAY_UPDATE

        # 2. Slot-specific delay on Slot 1 (only farmer 1 affected)
        u1_count_before = get_unread_count(u1.id)
        u2_count_before = get_unread_count(u2.id)

        create_delay(
            data={"centre_id": c1_id, "slot_id": slot1_id, "delay_date": "2026-09-20", "delay_minutes": 10},
            current_user_id=103,
        )

        assert get_unread_count(u1.id) == u1_count_before + 1
        assert get_unread_count(u2.id) == u2_count_before  # Farmer 2 not affected by slot 1 delay


def test_procurement_status_change_triggers(app, test_users, setup_domain):
    """Verify procurement status creation and update trigger notifications; unchanged status does not."""
    with app.app_context():
        u1, _, _ = test_users
        b1_id = setup_domain["b1_id"]

        count_start = get_unread_count(u1.id)

        # Create procurement
        p = create_procurement(
            booking_id=b1_id,
            data={"procurement_status": "COMPLETED", "quantity": 12.5, "unit": "quintal"},
        )
        assert get_unread_count(u1.id) == count_start + 1
        n = get_user_notifications(u1.id, limit=1)[0]
        assert n.notification_type == NotificationType.PROCUREMENT_UPDATE
        assert "COMPLETED" in n.title

        # Update without changing status (only remarks)
        count_mid = get_unread_count(u1.id)
        update_procurement(booking_id=b1_id, data={"remarks": "Checked quality"})
        assert get_unread_count(u1.id) == count_mid  # No duplicate notification


def test_payment_status_change_triggers(app, test_users, setup_domain):
    """Verify payment status creation and update trigger notifications without exposing sensitive details."""
    with app.app_context():
        u1, _, _ = test_users
        b1_id = setup_domain["b1_id"]

        count_start = get_unread_count(u1.id)

        # Create payment
        pm = create_payment(
            booking_id=b1_id,
            data={"payment_status": "PAID", "amount": 27500.0, "payment_reference": "TXN998877"},
        )
        assert get_unread_count(u1.id) == count_start + 1
        n = get_user_notifications(u1.id, limit=1)[0]
        assert n.notification_type == NotificationType.PAYMENT_UPDATE
        assert "PAID" in n.title
        assert "card" not in n.message.lower()
        assert "cvv" not in n.message.lower()

        # Update payment status
        update_payment(booking_id=b1_id, data={"payment_status": "PROCESSING"})
        assert get_unread_count(u1.id) == count_start + 2


# --- 5. Realtime Socket.IO Event Tests -----------------------------------------

def test_realtime_notification_event_post_commit(app, test_users):
    """Verify emit_notification_created is called post-commit with lightweight payload."""
    with app.app_context():
        u1 = test_users[0]
        with patch("app.queue.events.socketio.emit") as mock_emit:
            create_notification(
                user_id=u1.id,
                notification_type=NotificationType.DELAY_UPDATE,
                title="Realtime Delay Alert",
                message="Delay of 20 mins recorded.",
            )

            assert mock_emit.called
            args, kwargs = mock_emit.call_args
            assert args[0] == "notification_created"
            event_payload = args[1]
            assert kwargs["to"] == f"farmer_user_{u1.id}"
            assert kwargs["namespace"] == "/queue"

            assert event_payload["title"] == "Realtime Delay Alert"
            assert event_payload["type"] == NotificationType.DELAY_UPDATE
            assert "is_read" in event_payload


def test_realtime_no_emission_on_transaction_rollback(app, test_users):
    """Verify socket event is not emitted if DB transaction rolls back."""
    with app.app_context():
        u1 = test_users[0]
        with patch("app.queue.events.socketio.emit") as mock_emit:
            with pytest.raises(NotificationError):
                # Trigger db error by passing non-existent user_id with foreign key constraint enabled or invalid type
                with patch("app.extensions.db.session.commit", side_effect=Exception("DB Error")):
                    create_notification(u1.id, NotificationType.SYSTEM, "Rollback Test", "Msg")

            mock_emit.assert_not_called()


# --- 6. Browser Push Subscription Tests ---------------------------------------

def test_push_subscription_crud(app, test_users):
    """Verify saving and removing push subscriptions."""
    with app.app_context():
        u1 = test_users[0]
        endpoint = "https://fcm.googleapis.com/fcm/send/test-token-123"

        sub = save_push_subscription(
            user_id=u1.id,
            endpoint=endpoint,
            p256dh="mock_p256dh_key",
            auth="mock_auth_secret",
        )
        assert sub.id is not None
        assert sub.user_id == u1.id

        # Retrieve from DB
        db_sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
        assert db_sub is not None

        # Remove subscription
        removed = remove_push_subscription(u1.id, endpoint)
        assert removed is True
        assert PushSubscription.query.filter_by(endpoint=endpoint).first() is None


def test_api_push_subscribe_and_unsubscribe(client, test_users, app):
    """Verify POST and DELETE /api/notifications/push/subscribe."""
    payload = {
        "endpoint": "https://push.service.example.com/device-456",
        "keys": {
            "p256dh": "key_p256",
            "auth": "key_auth",
        }
    }

    # Subscribe
    res_sub = make_auth_call(client, "POST", "/api/notifications/push/subscribe", "sub-farmer-101", json_data=payload)
    assert res_sub.status_code == 201
    assert res_sub.get_json()["message"] == "Push subscription saved successfully"

    # Unsubscribe
    res_unsub = make_auth_call(
        client,
        "DELETE",
        f"/api/notifications/push/subscribe?endpoint={payload['endpoint']}",
        "sub-farmer-101",
    )
    assert res_unsub.status_code == 200
    assert res_unsub.get_json()["message"] == "Push subscription removed successfully"
